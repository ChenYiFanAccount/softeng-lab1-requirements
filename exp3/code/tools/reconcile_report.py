"""对账命令行（M10）：只读比对库存占用与有效订单汇总，打印差异清单。

两种用法：

- ``--db <路径>``：对既有库跑一次对账（只读，不改任何数据）；
- ``--demo``：在临时库里造一单，先跑平账（``diff=0``），再人为把某天占用 +1
  跑一次，打印带订单号与日期的告警——交付证据与报告截图都用这一段。

退出码固定为 0：对账发现差异不是"命令失败"，而是业务告警；调用方应读输出里的
``diff=`` 而不是退出码。真正需要非零退出的场景（如巡检脚本）可在外面包一层判断。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

# pylint: disable=wrong-import-position
from app.application.actor import Actor  # noqa: E402
from app.application.booking_service import BookingAppService  # noqa: E402
from app.application.clock import FrozenClock  # noqa: E402
from app.application.commands import PlaceBookingCommand  # noqa: E402
from app.application.reconcile_service import ReconcileService  # noqa: E402
from app.domain.enums import ActorRole, BookingEvent  # noqa: E402
from app.infrastructure.db import connection as db_connection  # noqa: E402
from app.infrastructure.db import migrate_runner  # noqa: E402

DEMO_START = date(2027, 3, 1)
DEMO_END = date(2027, 3, 5)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """命令行参数：``--db`` 与 ``--demo`` 二选一。"""
    parser = argparse.ArgumentParser(description="库存对账（只读）")
    parser.add_argument("--db", type=Path, help="既有数据库路径")
    parser.add_argument("--days", type=int, default=90, help="从今天起对账多少天（默认 90）")
    parser.add_argument("--hotel-id", type=int, default=None, help="只对某家酒店")
    parser.add_argument("--demo", action="store_true", help="在临时库里演示平账与差异两种输出")
    return parser.parse_args(argv)


def print_report(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    title: str,
    service: ReconcileService,
    start: date,
    end: date,
    hotel_id: int | None,
) -> None:
    """打印一次对账结果。"""
    report = service.check(start, end, hotel_id)
    print(f"--- {title} ---")
    print(f"range={report.start_date}~{report.end_date}")
    print(service.format_report(report))


def demo() -> None:
    """临时库里造一单，演示 ``diff=0`` 与告警两种输出。"""
    workspace = Path(tempfile.mkdtemp(prefix="reconcile-demo-"))
    db_path = workspace / "demo.db"
    conn = db_connection.connect(db_path)
    try:
        migrate_runner.apply_migrations(conn)
        stamp = "2026-11-25 00:00:00"
        hotel_id = int(
            conn.execute(
                "INSERT INTO hotel (name, address, phone, description, audit_status,"
                " created_at, audited_at) VALUES ('演示酒店', '演示路 1 号', '010-00000000',"
                " '对账演示', 'APPROVED', ?, ?)",
                (stamp, stamp),
            ).lastrowid
        )
        room_type_id = int(
            conn.execute(
                "INSERT INTO room_type (hotel_id, name, bed_type, area_sqm, capacity, total_rooms)"
                " VALUES (?, '演示大床房', '大床 1.8m', 30, 2, 5)",
                (hotel_id,),
            ).lastrowid
        )
        guest_id = int(
            conn.execute(
                "INSERT INTO user_account (login_name, password_hash, role, hotel_id, status,"
                " created_at) VALUES ('13900000001', 'x', 'CUSTOMER', NULL, 'ACTIVE', ?)",
                (stamp,),
            ).lastrowid
        )
        staff_id = int(
            conn.execute(
                "INSERT INTO user_account (login_name, password_hash, role, hotel_id, status,"
                " created_at) VALUES ('13900000002', 'x', 'HOTEL_STAFF', ?, 'ACTIVE', ?)",
                (hotel_id, stamp),
            ).lastrowid
        )
        day = DEMO_START
        while day < DEMO_END:
            conn.execute(
                "INSERT INTO room_inventory (room_type_id, stay_date, available_rooms,"
                " occupied_rooms, sale_status, updated_at) VALUES (?, ?, 5, 0, 'ON_SALE', ?)",
                (room_type_id, day.isoformat(), stamp),
            )
            conn.execute(
                "INSERT INTO room_price (room_type_id, stay_date, unit_price_cents, updated_at)"
                " VALUES (?, ?, 30000, ?)",
                (room_type_id, day.isoformat(), stamp),
            )
            day += timedelta(days=1)

        clock = FrozenClock(current=datetime(2027, 2, 1, 9, 0, 0))
        bookings = BookingAppService(conn, clock=clock)
        guest = Actor(account_id=guest_id, role=ActorRole.CUSTOMER, login_name="13900000001")
        staff = Actor(
            account_id=staff_id,
            role=ActorRole.HOTEL_STAFF,
            hotel_id=hotel_id,
            login_name="13900000002",
        )
        booking = bookings.place_booking(
            PlaceBookingCommand(
                guest_id=guest_id,
                hotel_id=hotel_id,
                room_type_id=room_type_id,
                check_in_date=date(2027, 3, 1),
                check_out_date=date(2027, 3, 3),
                room_count=2,
            ),
            guest,
        )
        bookings.apply_event(booking.booking_no, BookingEvent.CONFIRM, staff)

        service = ReconcileService(conn)
        print(f"demo_booking_no={booking.booking_no} room_type_id={room_type_id}")
        print_report("平账（库存占用与订单汇总一致）", service, DEMO_START, DEMO_END, None)

        conn.execute(
            "UPDATE room_inventory SET occupied_rooms = occupied_rooms + 1"
            " WHERE room_type_id = ? AND stay_date = '2027-03-02'",
            (room_type_id,),
        )
        print_report("人为把 2027-03-02 的占用 +1 之后", service, DEMO_START, DEMO_END, None)
        print("check=passed")
    finally:
        conn.close()
        shutil.rmtree(workspace, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """入口：``--demo`` 演示，或对 ``--db`` 指定的库跑一次只读对账。"""
    args = parse_args(argv)
    if args.demo:
        demo()
        return 0
    if args.db is None:
        print("用法：reconcile_report.py --db <路径> 或 --demo")
        return 0
    if not args.db.exists():
        print(f"数据库不存在：{args.db}")
        return 0
    conn = db_connection.connect(args.db)
    try:
        today = date.today()
        print_report(
            f"对账 {args.db.name}",
            ReconcileService(conn),
            today,
            today + timedelta(days=args.days),
            args.hotel_id,
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
