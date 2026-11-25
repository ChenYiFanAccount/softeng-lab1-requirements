"""迁移工具：把库升到 ``migrations/`` 里的最新版本（S1-3 的判定命令）。

用法::

    python code/tools/migrate.py --db code/data/app.db

幂等：连跑两次，第二次输出 ``applied=none``、``user_version`` 不变、行数不变。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.infrastructure.db import connection as db_connection  # noqa: E402
from app.infrastructure.db import migrate_runner  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="执行数据库迁移（幂等）")
    parser.add_argument("--db", default=None, help="数据库文件路径，默认取 config/settings.json")
    parser.add_argument("--target", type=int, default=None, help="目标版本，默认最新")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """入口：打印升级前后的版本与行数快照。"""
    args = parse_args(argv)
    db_path = Path(args.db).resolve() if args.db else db_connection.default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = db_connection.connect(db_path)
    try:
        before = migrate_runner.current_version(conn)
        counts_before = migrate_runner.row_counts(conn) if _has_tables(conn) else {}
        applied = migrate_runner.apply_migrations(conn, target_version=args.target)
        after = migrate_runner.current_version(conn)
        counts_after = migrate_runner.row_counts(conn)

        print(f"db={db_path}")
        print(f"user_version_before={before}")
        print(f"applied={applied or 'none'}")
        print(f"user_version={after}")
        print("rows_before=" + " ".join(f"{k}={v}" for k, v in counts_before.items()))
        print("rows_after=" + " ".join(f"{k}={v}" for k, v in counts_after.items()))
        if not applied:
            print("status=up_to_date")
        return 0
    finally:
        conn.close()


def _has_tables(conn) -> bool:  # noqa: ANN001 - 简单内部判定，避免为注解引入额外 import
    """判断库里是否已有业务表（首次建库时行数快照为空）。"""
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()
    return int(row[0]) > 0


if __name__ == "__main__":
    raise SystemExit(main())
