"""一键建库：迁移 + 种子 + PRAGMA 自检（S1-1 / S1-2 / S1-4 的判定命令）。

用法::

    python code/tools/init_db.py --db code/data/app.db --seed

输出固定字段，便于评审直接比对：``tables=12``、四项 PRAGMA、``user_version``、
六张种子表的行数。任一项不符合 S1 判据时以退出码 1 结束（避免"看着成功"）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.infrastructure.db import connection as db_connection  # noqa: E402
from app.infrastructure.db import migrate_runner, seed as seed_module  # noqa: E402

#: S1-2 期望的日志模式
EXPECTED_JOURNAL_MODE = "WAL"

#: S1-4 种子规模：表名 → (最小行数, 精确行数或 None)
SEED_EXPECTATIONS: dict[str, tuple[int, int | None]] = {
    "hotel": (3, 3),
    "room_type": (8, 8),
    "room_inventory": (720, 720),
    "room_price": (720, 720),
    "user_account": (4, None),
    "holiday_calendar": (1, None),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="初始化酒店预订演示库（SQLite）")
    parser.add_argument("--db", default=None, help="数据库文件路径，默认取 config/settings.json")
    parser.add_argument("--seed", action="store_true", help="写入种子数据（幂等，已有数据则跳过）")
    parser.add_argument("--reset", action="store_true", help="先清空全部业务表再建库（会丢数据）")
    parser.add_argument("--no-check", action="store_true", help="只建库，不校验 S1 判据")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """入口：建库、种子、打印证据，返回进程退出码。"""
    args = parse_args(argv)
    db_path = Path(args.db).resolve() if args.db else db_connection.default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    settings = db_connection.load_settings()

    conn = db_connection.connect(db_path)
    try:
        if args.reset:
            migrate_runner.apply_migrations(conn)
            seed_module.clear_all(conn)
            print("reset=yes")

        applied = migrate_runner.apply_migrations(conn)
        print(f"migrations_applied={applied or 'none'}")

        if args.seed:
            outcome = seed_module.seed_all(conn, settings)
            print(f"seed_applied={outcome.applied}")

        print(f"db={db_path}")
        tables = migrate_runner.table_names(conn)
        print(f"tables={len(tables)}")
        print(f"tables_list={','.join(tables)}")

        snapshot = db_connection.pragma_snapshot(conn)
        print(f"foreign_keys={snapshot['foreign_keys']}")
        print(f"foreign_key_check={snapshot['foreign_key_check']}")
        print(f"integrity_check={snapshot['integrity_check']}")
        print(f"journal_mode={str(snapshot['journal_mode']).lower()}")
        print(f"user_version={migrate_runner.current_version(conn)}")

        counts = migrate_runner.row_counts(conn)
        print("rows=" + " ".join(f"{name}={count}" for name, count in counts.items()))
        if args.no_check:
            return 0
        return _verify(tables, snapshot, counts)
    finally:
        conn.close()


def _verify(
    tables: list[str],
    snapshot: dict[str, object],
    counts: dict[str, int],
) -> int:
    """逐条比对 S1 判据，返回 0 表示全过，1 表示有偏差（并把原因打出来）。"""
    problems: list[str] = []
    if len(tables) != 12:
        problems.append(f"tables={len(tables)}，期望 12")
    if int(snapshot["foreign_keys"]) != 1:  # type: ignore[arg-type]
        problems.append(f"foreign_keys={snapshot['foreign_keys']}，期望 1")
    if snapshot["foreign_key_check"]:
        problems.append(f"foreign_key_check 非空：{snapshot['foreign_key_check']}")
    if str(snapshot["integrity_check"]).lower() != "ok":
        problems.append(f"integrity_check={snapshot['integrity_check']}，期望 ok")
    if str(snapshot["journal_mode"]).upper() != EXPECTED_JOURNAL_MODE:
        problems.append(f"journal_mode={snapshot['journal_mode']}，期望 {EXPECTED_JOURNAL_MODE}")

    for table, (minimum, exact) in SEED_EXPECTATIONS.items():
        actual = counts.get(table, 0)
        if actual < minimum:
            problems.append(f"{table}={actual}，期望 ≥{minimum}")
        elif exact is not None and actual != exact:
            problems.append(f"{table}={actual}，期望 ={exact}")

    if not problems:
        print("check=passed")
        return 0
    print("check=failed")
    for problem in problems:
        print(f"  - {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
