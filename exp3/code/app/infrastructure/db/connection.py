"""SQLite 连接工厂与事务封装。

四条设计要点（对应 `exp3/实验三_执行方案.md` §C.3 与 P0 评审 R1-05）：

1. ``isolation_level=None``：让 DB-API 驱动彻底退出事务管理，事务边界全部由
   本模块显式控制。默认值 ``""`` 会在第一条 DML 前隐式 ``BEGIN``，之后再执行
   ``BEGIN IMMEDIATE`` 就会抛 ``cannot start a transaction within a transaction``
   —— 这正是 P0 第 1 轮评审抓到的缺陷。
2. **每线程独立连接**：``check_same_thread`` 保持为 ``True``，连接不跨线程复用；
   共享连接在 SQLite 下会把并发压成串行，还会踩到游标互相覆盖的问题。
3. **写事务一律 ``BEGIN IMMEDIATE``**：下单是「先读余量、再改占用」，若用默认的
   deferred 事务，两个线程可能同时读到同一个旧余量后再各自升级写锁，产生
   ``SQLITE_BUSY`` 或写偏。IMMEDIATE 在事务开头就拿写锁，把读-改-写整体串行化。
4. **显式 ``busy_timeout``**：不设时默认 0，锁冲突立即报 ``database is locked``；
   设成毫秒数后，等待锁的线程会重试而不是失败。

只读查询同样走本工厂，以保证 ``foreign_keys``、``journal_mode`` 等 PRAGMA 一致。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

#: settings.json 相对 `code/` 目录的路径
SETTINGS_RELATIVE_PATH = Path("config") / "settings.json"

#: 未配置时的兜底值，与 settings.json 保持一致
DEFAULT_BUSY_TIMEOUT_MS = 5000
DEFAULT_JOURNAL_MODE = "WAL"


def code_root() -> Path:
    """返回 `code/` 目录（`app/infrastructure/db/connection.py` 向上三级）。"""
    return Path(__file__).resolve().parents[3]


def load_settings(settings_path: Path | None = None) -> dict[str, Any]:
    """读取并解析 `code/config/settings.json`。

    Args:
        settings_path: 可选的显式路径；默认取 `code/config/settings.json`。

    Returns:
        解析后的配置字典。

    Raises:
        FileNotFoundError: 配置文件不存在。
        ValueError: 文件内容不是合法的 JSON 对象。
    """
    path = settings_path or (code_root() / SETTINGS_RELATIVE_PATH)
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"配置文件顶层必须是对象：{path}")
    return data


def default_db_path(settings_path: Path | None = None) -> Path:
    """按配置计算默认数据库文件路径（相对 `code/` 解析）。"""
    settings = load_settings(settings_path)
    relative = settings.get("database", {}).get("path", "data/app.db")
    return (code_root() / relative).resolve()


def connect(
    db_path: str | Path,
    busy_timeout_ms: int | None = None,
    *,
    journal_mode: str | None = None,
) -> sqlite3.Connection:
    """打开一个已配好 PRAGMA 的 SQLite 连接。

    Args:
        db_path: 数据库文件路径；父目录必须已存在。
        busy_timeout_ms: 写锁等待毫秒数；None 表示用配置值。
        journal_mode: 日志模式；None 表示用配置值（默认 WAL）。

    Returns:
        处于自动提交模式（``isolation_level=None``）的连接，行工厂为
        :class:`sqlite3.Row`，可按列名取值。
    """
    settings = load_settings()
    db_settings = settings.get("database", {})
    timeout_ms = int(
        busy_timeout_ms
        if busy_timeout_ms is not None
        else db_settings.get("busy_timeout_ms", DEFAULT_BUSY_TIMEOUT_MS)
    )
    mode = journal_mode or db_settings.get("journal_mode", DEFAULT_JOURNAL_MODE)
    synchronous = db_settings.get("synchronous", "NORMAL")

    conn = sqlite3.connect(
        database=str(db_path),
        timeout=timeout_ms / 1000.0,
        isolation_level=None,  # 关键：驱动不再隐式开事务
        check_same_thread=True,
    )
    conn.row_factory = sqlite3.Row
    apply_pragmas(conn, busy_timeout_ms=timeout_ms, journal_mode=mode, synchronous=synchronous)
    return conn


def apply_pragmas(
    conn: sqlite3.Connection,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    journal_mode: str = DEFAULT_JOURNAL_MODE,
    synchronous: str = "NORMAL",
) -> None:
    """设置连接级 PRAGMA；顺序有意义，``busy_timeout`` 必须在可能加锁的语句之前。"""
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA journal_mode = {journal_mode}")
    conn.execute(f"PRAGMA synchronous = {synchronous}")


@contextmanager
def immediate_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """以 ``BEGIN IMMEDIATE`` 开启写事务，异常时回滚。

    用法::

        with immediate_transaction(conn):
            conn.execute("UPDATE room_inventory SET occupied_rooms = occupied_rooms + 1")

    Args:
        conn: 由 :func:`connect` 打开、处于自动提交模式的连接。

    Yields:
        同一个连接，便于链式书写。

    Raises:
        RuntimeError: 连接上已有未结束的事务（嵌套事务 SQLite 不支持）。
    """
    if conn.in_transaction:
        raise RuntimeError("检测到未结束的事务：SQLite 不支持嵌套事务，请先提交或回滚")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def pragma_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """采集 S1-2 要求的四项 PRAGMA，供工具脚本与测试打印。

    Returns:
        键为 ``foreign_keys`` / ``foreign_key_check`` / ``integrity_check`` /
        ``journal_mode`` 的字典；``foreign_key_check`` 为违规行列表（空表示通过）。
    """
    foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    violations = [dict(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall()]
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    return {
        "foreign_keys": foreign_keys,
        "foreign_key_check": violations,
        "integrity_check": integrity,
        "journal_mode": str(journal).upper(),
    }
