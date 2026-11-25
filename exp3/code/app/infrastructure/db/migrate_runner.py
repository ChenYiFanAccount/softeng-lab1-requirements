"""迁移执行器：按 ``migrations/NNNN_*.sql`` 顺序升级 ``PRAGMA user_version``。

为什么不用 ``executescript``：它在执行前会先 ``COMMIT`` 掉当前事务，一个迁移脚本
中途失败就会留下半张表。这里用 :func:`sqlite3.complete_statement` 逐条切分语句，
在同一个 ``BEGIN IMMEDIATE`` 里执行完再写版本号，失败整体回滚（DDL 在 SQLite 中
也是可回滚的）。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .connection import immediate_transaction

#: 迁移文件命名：`0001_init.sql`
MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")

#: 默认迁移目录
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

#: 建表语句之外的内部表前缀，统计 ``tables=12`` 时要排除
SYSTEM_TABLE_PREFIXES = ("sqlite_",)


@dataclass(frozen=True)
class Migration:
    """一个迁移文件。"""

    version: int
    name: str
    path: Path


def discover_migrations(directory: Path | None = None) -> list[Migration]:
    """扫描迁移目录，按版本号升序返回。

    Args:
        directory: 迁移目录；默认为本包下的 ``migrations/``。

    Returns:
        迁移列表；版本号重复或文件名不合规时抛 ``ValueError``。
    """
    base = directory or MIGRATIONS_DIR
    found: list[Migration] = []
    for path in sorted(base.glob("*.sql")):
        match = MIGRATION_PATTERN.match(path.name)
        if not match:
            raise ValueError(f"迁移文件名不合规（应形如 0001_init.sql）：{path.name}")
        found.append(Migration(int(match.group("version")), match.group("name"), path))
    versions = [item.version for item in found]
    if len(versions) != len(set(versions)):
        raise ValueError(f"迁移版本号重复：{versions}")
    return sorted(found, key=lambda item: item.version)


def current_version(conn: sqlite3.Connection) -> int:
    """读取 ``PRAGMA user_version``。"""
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def split_statements(script: str) -> list[str]:
    """按 SQLite 的语句边界切分脚本，跳过纯注释片段。

    Args:
        script: 整个 ``.sql`` 文件的内容。

    Returns:
        可逐条 ``execute`` 的语句列表。
    """
    statements: list[str] = []
    buffer = ""
    for char in script:
        buffer += char
        if char == ";" and sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if not _is_comment_only(statement):
                statements.append(statement)
    tail = buffer.strip()
    if tail and not _is_comment_only(tail):
        statements.append(tail)
    return statements


def _is_comment_only(statement: str) -> bool:
    """判断片段是否只有注释与空白（这类片段不必执行）。"""
    meaningful = [
        line.strip()
        for line in statement.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]
    return not meaningful


def apply_migrations(
    conn: sqlite3.Connection,
    directory: Path | None = None,
    target_version: int | None = None,
) -> list[int]:
    """把数据库升级到最新（或指定）版本，返回本次实际应用的版本号列表。

    Args:
        conn: 由 :func:`app.infrastructure.db.connection.connect` 打开的连接。
        directory: 迁移目录；默认包内 ``migrations/``。
        target_version: 目标版本；None 表示升到最新。

    Returns:
        本次应用的版本号，已是最新时为空列表。

    Raises:
        ValueError: 库里记录的版本高于代码里的最新版本（代码回退）。
    """
    migrations = discover_migrations(directory)
    latest = migrations[-1].version if migrations else 0
    target = latest if target_version is None else int(target_version)
    if target > latest:
        raise ValueError(f"目标版本 {target} 超过代码内最新版本 {latest}")

    version = current_version(conn)
    if version > latest:
        raise ValueError(
            f"数据库 user_version={version} 高于代码最新版本 {latest}，请勿用旧代码打开新库"
        )

    applied: list[int] = []
    for migration in migrations:
        if migration.version <= version or migration.version > target:
            continue
        statements = split_statements(migration.path.read_text(encoding="utf-8"))
        # 复用连接层的写事务封装：一个迁移脚本要么整份生效，要么一条表都不留。
        with immediate_transaction(conn):
            for statement in statements:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {migration.version:d}")
        applied.append(migration.version)
        version = migration.version
    return applied


def table_names(conn: sqlite3.Connection) -> list[str]:
    """列出业务表（排除 ``sqlite_*`` 内部表），按名称排序。"""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    return [
        str(row["name"])
        for row in rows
        if not str(row["name"]).startswith(SYSTEM_TABLE_PREFIXES)
    ]


def row_counts(conn: sqlite3.Connection, tables: list[str] | None = None) -> dict[str, int]:
    """统计各表行数（表名来自 ``sqlite_master``，不接受外部拼串）。"""
    names = table_names(conn) if tables is None else tables
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
    return counts
