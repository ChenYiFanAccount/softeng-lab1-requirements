"""后台调度入口：在**独立线程 + 独立连接**里跑一轮履约扫描（S4-5）。

为什么单独一个工具而不是塞进应用服务：调度器的职责就是"到点触发"，它需要的是
（1）不依赖任何 HTTP 请求、（2）自己建连接不跨线程复用、（3）跑完能退出并给出
可判定的输出。S4-5 要求"后台线程不炸库"，最直接的验证就是本脚本：它在
``threading.Thread`` 里 ``connect()``，若把主线程的连接传进去，SQLite 会抛
``ProgrammingError: SQLite objects created in a thread can only be used in that
same thread``——本脚本刻意不这么做。

设备无关的时间判断全部在 ``FulfillmentService`` 里，本脚本不自己算时间。
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from typing import Any, Sequence

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.application.clock import SystemClock
from app.application.fulfillment_service import FulfillmentService
from app.infrastructure.db.connection import connect, default_db_path, load_settings
from app.infrastructure.db.migrate_runner import apply_migrations, table_names
from app.infrastructure.db.seed import seed_all


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="跑一轮履约扫描（超时取消 / 自动入住 / no-show）")
    parser.add_argument("--db", default=None, help="数据库文件路径；省略时按 settings.json 解析")
    parser.add_argument("--timeout-minutes", type=int, default=None, help="覆盖待确认超时分钟数")
    parser.add_argument("--no-show-cutoff", default=None, help="覆盖当日 no-show 判定时刻，如 23:59")
    parser.add_argument("--seed-if-empty", action="store_true", help="库为空时自动灌种子数据")
    return parser.parse_args(argv)


def ensure_schema(db_path: Path, settings: dict[str, Any], seed_if_empty: bool) -> dict[str, int]:
    """建表（幂等）并在需要时灌种子；返回各表行数，供打印。"""
    conn = connect(db_path, settings.get("database", {}).get("busy_timeout_ms"))
    try:
        apply_migrations(conn)
        if seed_if_empty and "hotel" in table_names(conn):
            rows = conn.execute("SELECT COUNT(*) FROM hotel").fetchone()[0]
            if int(rows) == 0:
                seed_all(conn, settings)
        counts = {}
        for name in table_names(conn):
            counts[name] = int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        return counts
    finally:
        conn.close()


def scan_in_background(db_path: Path, settings: dict[str, Any]) -> dict[str, Any]:
    """在后台线程里跑一轮扫描，返回 ``ScanReport.to_dict()``。

    连接在**线程内部**创建、线程内部关闭，主线程不碰它——这是 S4-5 的考点。
    """
    result: dict[str, Any] = {}
    failure: list[BaseException] = []

    def worker() -> None:
        conn = connect(db_path, settings.get("database", {}).get("busy_timeout_ms"))
        try:
            service = FulfillmentService(conn, clock=SystemClock(), settings=settings)
            result.update(service.scan_once().to_dict())
        except BaseException as error:  # pylint: disable=broad-exception-caught
            failure.append(error)
        finally:
            conn.close()

    thread = threading.Thread(target=worker, name="fulfillment-scan", daemon=False)
    thread.start()
    thread.join()
    if failure:
        raise failure[0]
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：建库（可选）→ 后台线程扫描 → 打印统计。"""
    args = parse_args(argv)
    settings = load_settings()
    block = settings.setdefault("fulfillment", {})
    if args.timeout_minutes is not None:
        block["pending_timeout_minutes"] = args.timeout_minutes
    if args.no_show_cutoff is not None:
        block["no_show_cutoff"] = args.no_show_cutoff

    db_path = Path(args.db) if args.db else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    counts = ensure_schema(db_path, settings, args.seed_if_empty)
    report = scan_in_background(db_path, settings)

    print(f"db={db_path}")
    print(
        f"tables={len(counts)} rows_hotel={counts.get('hotel', 0)}"
        f" rows_booking={counts.get('booking', 0)}"
    )
    print("background_thread_ok=True")
    for key in (
        "scanned_at",
        "scanned_at_local",
        "timezone",
        "timeouts",
        "auto_check_ins",
        "no_shows",
        "failures",
        "total",
    ):
        print(f"{key}={report[key]}")
    print("check=passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
