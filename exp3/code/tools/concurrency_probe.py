"""并发不超卖探针：200 个线程同时抢同一晚的最后一间房。

用法（S3-2 判据命令）::

    python code/tools/concurrency_probe.py --threads 200 --rooms 1

期望输出（数字必须一模一样）::

    success=1
    fail=199
    locked_errors=0
    negative_stock=0
    booking_rows=1
    booking_night_rows=1

设计要点：

- 每个线程**各自** ``connect()`` 一条连接（``sqlite3`` 连接不可跨线程共享），
  用 ``threading.Barrier`` 让 200 个请求在同一瞬间冲进去；
- **不重试**：锁冲突就记 ``locked_errors``，绝不 sleep 后重来——重试会把
  "锁没生效"包装成"最终也成功了"，正好掩盖要证明的东西；
- 每单用不同顾客，避免被 U6 索引的"同顾客重复预订"提前拦下；
- 空库现场建（迁移 + 最小夹具），跑完即删，不污染 ``code/data/app.db``。
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:  # pylint: disable=wrong-import-position
    sys.path.insert(0, str(CODE_ROOT))

from app.application.booking_service import BookingAppService  # pylint: disable=wrong-import-position
from app.application.commands import PlaceBookingCommand  # pylint: disable=wrong-import-position
from app.domain.errors import DomainError  # pylint: disable=wrong-import-position
from app.infrastructure.db.connection import connect  # pylint: disable=wrong-import-position
from app.infrastructure.db.migrate_runner import apply_migrations  # pylint: disable=wrong-import-position

#: 夹具里的时间戳（UTC 文本，与全库口径一致）
NOW_TEXT = "2026-11-25 00:00:00"

#: 结果分类
OK = "ok"
SOLD_OUT = "sold_out"
LOCKED = "locked"
ERROR = "error"


@dataclass
class Outcome:
    """一次探针的统计结果。"""

    success: int = 0
    fail: int = 0
    locked_errors: int = 0
    elapsed_ms: float = 0.0
    failures: dict[str, int] = field(default_factory=dict)
    unexpected: list[str] = field(default_factory=list)

    def record(self, kind: str, detail: str = "") -> None:
        """按结果分类累加（线程内调用后由主线程汇总）。"""
        if kind == OK:
            self.success += 1
            return
        self.fail += 1
        key = ERROR if kind.startswith(ERROR) else kind
        self.failures[key] = self.failures.get(key, 0) + 1
        if kind == LOCKED:
            self.locked_errors += 1
        elif kind.startswith(ERROR):
            self.unexpected.append(detail)


def build_fixture(db_path: Path, threads: int, check_in: date, check_out: date) -> None:
    """建库并塞入最小夹具：1 家酒店、1 个房型、``threads`` 个顾客、1 间可售。"""
    conn = connect(db_path, busy_timeout_ms=10000)
    try:
        apply_migrations(conn)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO hotel (id, name, address, phone, audit_status, created_at) "
            "VALUES (1, ?, ?, ?, 'APPROVED', ?)",
            ("并发探针酒店", "测试路 1 号", "021-00000000", NOW_TEXT),
        )
        cur.execute(
            "INSERT INTO room_type (id, hotel_id, name, bed_type, area_sqm, capacity, total_rooms) "
            "VALUES (1, 1, ?, ?, 25, 2, 5)",
            ("标准大床房", "大床"),
        )
        for index in range(threads):
            cur.execute(
                "INSERT INTO user_account (id, login_name, password_hash, role, created_at) "
                "VALUES (?, ?, 'x', 'CUSTOMER', ?)",
                (1000 + index, f"probe{index:03d}", NOW_TEXT),
            )
        night = check_in
        while night < check_out:
            cur.execute(
                "INSERT INTO room_inventory "
                "(room_type_id, stay_date, available_rooms, occupied_rooms,"
                " sale_status, updated_at) "
                "VALUES (1, ?, 1, 0, 'ON_SALE', ?)",
                (night.isoformat(), NOW_TEXT),
            )
            cur.execute(
                "INSERT INTO room_price (room_type_id, stay_date, unit_price_cents, updated_at) "
                "VALUES (1, ?, 30000, ?)",
                (night.isoformat(), NOW_TEXT),
            )
            night += timedelta(days=1)
    finally:
        conn.close()


def attempt(db_path: Path, guest_id: int, check_in: date, check_out: date, rooms: int) -> str:
    """一个线程抢一次房；返回结果分类，异常一律不外抛（交主线程统计）。"""
    conn = None
    try:
        conn = connect(db_path, busy_timeout_ms=10000)
        service = BookingAppService(conn)
        service.place_booking(
            PlaceBookingCommand(
                guest_id=guest_id,
                hotel_id=1,
                room_type_id=1,
                check_in_date=check_in,
                check_out_date=check_out,
                room_count=rooms,
            )
        )
        return OK
    except sqlite3.OperationalError as error:
        if "locked" in str(error).lower() or "busy" in str(error).lower():
            return LOCKED
        return f"{ERROR}:{error}"
    except DomainError:
        # 余量不足 / 重复预订都是"正常的失败"，这里统一记 sold_out
        return SOLD_OUT
    except Exception as error:  # pylint: disable=broad-exception-caught
        return f"{ERROR}:{type(error).__name__}: {error}"
    finally:
        if conn is not None:
            conn.close()


def run(db_path: Path, threads: int, rooms: int, check_in: date, check_out: date) -> Outcome:
    """拉起 200 个线程并汇总结果。"""
    barrier = threading.Barrier(threads)
    outcome = Outcome()
    lock = threading.Lock()

    def worker(index: int) -> None:
        barrier.wait()
        kind = attempt(db_path, 1000 + index, check_in, check_out, rooms)
        with lock:
            outcome.record(kind, kind)

    threads_list = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    started = time.perf_counter()
    for thread in threads_list:
        thread.start()
    for thread in threads_list:
        thread.join()
    outcome.elapsed_ms = (time.perf_counter() - started) * 1000
    return outcome


def count_rows(db_path: Path) -> tuple[int, int, int]:
    """读回三条硬指标：订单行数、逐晚快照行数、坏库存行数。"""
    conn = connect(db_path, busy_timeout_ms=10000)
    try:
        booking_rows = int(conn.execute("SELECT COUNT(*) AS n FROM booking").fetchone()["n"])
        night_rows = int(conn.execute("SELECT COUNT(*) AS n FROM booking_night").fetchone()["n"])
        negative = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM room_inventory "
                "WHERE occupied_rooms < 0 OR occupied_rooms > available_rooms"
            ).fetchone()["n"]
        )
        return booking_rows, night_rows, negative
    finally:
        conn.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="并发不超卖探针")
    parser.add_argument("--threads", type=int, default=200, help="并发线程数")
    parser.add_argument("--rooms", type=int, default=1, help="每单间数")
    parser.add_argument("--keep", action="store_true", help="保留临时库便于事后排查")
    parser.add_argument(
        "--timing",
        action="store_true",
        help="额外打印用时（默认不打印：S7-6 要求三次输出逐字节一致，用时每次都不同）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """跑一次探针并按判据打印统计，全部达标返回 0。"""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.threads < 2 or args.rooms < 1:
        print("threads 必须 ≥2，rooms 必须 ≥1")
        return 2
    workdir = Path(tempfile.mkdtemp(prefix="concurrency-probe-"))
    db_path = workdir / "probe.db"
    check_in = date(2027, 3, 1)
    check_out = check_in + timedelta(days=1)
    try:
        build_fixture(db_path, args.threads, check_in, check_out)
        outcome = run(db_path, args.threads, args.rooms, check_in, check_out)
        booking_rows, night_rows, negative = count_rows(db_path)
        elapsed = outcome.elapsed_ms
        print(f"threads={args.threads} rooms={args.rooms} nights=1")
        print(f"success={outcome.success}")
        print(f"fail={outcome.fail}")
        print(f"locked_errors={outcome.locked_errors}")
        print(f"negative_stock={negative}")
        print(f"booking_rows={booking_rows}")
        print(f"booking_night_rows={night_rows}")
        print(f"failure_breakdown={outcome.failures}")
        if args.timing:
            print(f"elapsed_ms={elapsed:.1f}")
        if outcome.unexpected:
            for line in outcome.unexpected[:5]:
                print(f"unexpected={line}")
        passed = (
            outcome.success == 1
            and outcome.fail == args.threads - 1
            and outcome.locked_errors == 0
            and negative == 0
            and booking_rows == 1
            and night_rows == 1
        )
        print("check=passed" if passed else "check=failed")
        return 0 if passed else 1
    finally:
        if args.keep:
            print(f"db={db_path}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
