"""对账命令行（M10）：只读比对库存占用与有效订单汇总，打印差异清单。

三种用法：

- ``--db <路径>``：对既有库跑一次对账（只读，不改任何数据）；
- ``--demo``：在临时库里造一单，依次演示三段——
  1. 已确认单的平账（``diff=0``）；
  2. **走完入住 + 退房的单**仍然平账，且这两天营收不为零（G3-R1-01 的回归段）；
  3. 人为把某天占用 +1，打印带订单号与日期的告警；
- 退出码固定为 0：对账发现差异不是"命令失败"，而是业务告警；调用方应读输出里的
  ``diff=`` 而不是退出码。真正需要非零退出的场景（如巡检脚本）可在外面包一层判断。

第 2 段是必须的：旧 demo 只有 PENDING/CONFIRMED，永远碰不到"退房后口径"这条路径，
`CHECKED_OUT` 被排除在报表集合外的缺陷就是这样躲过了所有演示。
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
from app.application.report_service import ReportService  # noqa: E402
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


def print_revenue(conn, start: date, end: date) -> None:  # noqa: ANN001
    """打印区间内逐日营收：退房后这些数字必须仍然存在（G3-R1-01 的回归点）。"""
    revenue = ReportService(conn).revenue_by_day(start, end)
    print("--- 退房后营收（按入住日归属，不得为 0） ---")
    for row in revenue:
        print(f"revenue stay_date={row.stay_date} cents={row.revenue_cents}")
    print(f"revenue_total_cents={sum(row.revenue_cents for row in revenue)}")


def complete_stay(bookings: BookingAppService, booking_no: str, staff: Actor) -> None:
    """把订单推进到已退房（入住 → 退房），用于演示退房后的报表与对账口径。"""
    bookings.apply_event(booking_no, BookingEvent.CHECK_IN, staff)
    bookings.apply_event(booking_no, BookingEvent.CHECK_OUT, staff)


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
        print_report("平账（已确认单，库存占用与订单汇总一致）", service, DEMO_START, DEMO_END, None)

        # 第 2 段：走完 入住 → 退房。退房不释放占用，所以两侧必须仍然同集合；
        # 同时这两天营收不得归零（旧实现把 CHECKED_OUT 排除，营收会凭空消失）。
        complete_stay(bookings, booking.booking_no, staff)
        print_report(
            "含已完成订单（已退房）的平账：退房不释放占用，两侧仍同集合",
            service,
            DEMO_START,
            DEMO_END,
            None,
        )
        print_revenue(conn, DEMO_START, DEMO_END)

        conn.execute(
            "UPDATE room_inventory SET occupied_rooms = occupied_rooms + 1"
            " WHERE room_type_id = ? AND stay_date = '2027-03-02'",
            (room_type_id,),
        )
        print_report(
            "人为把 2027-03-02 的占用 +1 之后（告警必须带订单号）",
            service,
            DEMO_START,
            DEMO_END,
            None,
        )

        # 第 3 段：给一个**没有任何订单**的日期加占用，告警要写出可读原因而不是裸 "-"。
        conn.execute(
            "UPDATE room_inventory SET occupied_rooms = occupied_rooms + 1"
            " WHERE room_type_id = ? AND stay_date = '2027-03-04'",
            (room_type_id,),
        )
        print_report(
            "再给 2027-03-04（无任何订单）加 1 间占用：告警不得只写 bookings=-",
            service,
            DEMO_START,
            DEMO_END,
            None,
        )
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
