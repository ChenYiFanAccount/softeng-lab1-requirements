"""桌面程序入口：``python code/run.py``。

职责只有三件：确保库结构与种子数据在位、建主窗口、进事件循环。
库不存在时自动建（等于替用户跑一次 ``init_db --seed``），所以换一台机器也能直接启动。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.infrastructure.db.connection import (  # noqa: E402
    connect,
    default_db_path,
    load_settings,
)
from app.infrastructure.db.migrate_runner import apply_migrations, table_names  # noqa: E402
from app.infrastructure.db.seed import seed_all  # noqa: E402
from app.ui.app import run  # noqa: E402


def ensure_database(db_path: Path) -> sqlite3.Connection:
    """连库并按需建表、灌种子；返回可用的连接。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    if "hotel" not in table_names(conn):
        apply_migrations(conn)
    seed_all(conn, load_settings())
    return conn


def main(argv: list[str]) -> int:
    """连库 → 起窗口；`--db` 可指定别的库文件（演示用）。"""
    settings = load_settings()
    target = Path(argv[1]) if len(argv) > 1 else default_db_path(settings)
    conn = ensure_database(target)
    try:
        run(conn=conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
