"""S3-1：三条主链路端到端（下单→确认→入住→退房 / 改期 / 顾客取消）。

全部用例都走真实 SQLite（临时库 + 迁移 + 最小夹具），不打桩仓储——
S3 要证明的正是"仓储 SQL + 事务 + 状态机"合起来是对的，打桩就证明不了。
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from datetime import datetime

try:  # 两种跑法：`-m unittest code.tests.x` 与 `discover -s code/tests -t code`
    from code.tests import support
except ImportError:  # pragma: no cover - discover 模式
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring
# 每个用例的**名字**就是它要证明的命题（S2-2/S2-4 判据还要求名字里带关键数字），
# 再补一行 docstring 只会把同一句话写两遍；helper 与夹具依然要求 docstring。

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import FrozenClock
from app.application.commands import PlaceBookingCommand, RescheduleCommand
from app.application.errors import ConflictError
from app.domain.enums import ActorRole, BookingEvent, BookingStatus
from app.domain.errors import DuplicateBookingError

#: 夹具覆盖的日期（够跑"改期到更晚"的场景）
STAY_DATES = ("2027-03-01", "2027-03-02", "2027-03-03", "2027-03-04",
              "2027-03-05", "2027-03-06")


class FlowTestBase(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """公共装配：临时库、夹具、可注入时钟、三个角色。"""

    def setUp(self) -> None:
        self._stack = ExitStack()
        self.conn, self.path = self._stack.enter_context(support.temp_database())
        self.fix = support.insert_fixture(self.conn)
        for day in STAY_DATES:
            support.insert_inventory(self.conn, self.fix["room_type_id"], day, 5)
        self.clock = FrozenClock(datetime(2026, 11, 25, 9, 0, 0))
        self.service = BookingAppService(self.conn, clock=self.clock)
        self.guest = Actor(self.fix["guest_id"], ActorRole.CUSTOMER, login_name="13900000001")
        self.staff = Actor(
            self.fix["staff_id"],
            ActorRole.HOTEL_STAFF,
            hotel_id=self.fix["hotel_id"],
            login_name="13900000002",
        )

    def tearDown(self) -> None:
        self._stack.close()

    # ---------------------------------------------------------------- 工具

    def place(self, check_in: str = "2027-03-01", check_out: str = "2027-03-03",
              key: str | None = None):
        """以顾客身份下一单。"""
        return self.service.place_booking(
            PlaceBookingCommand(
                guest_id=self.fix["guest_id"],
                hotel_id=self.fix["hotel_id"],
                room_type_id=self.fix["room_type_id"],
                check_in_date=datetime.strptime(check_in, "%Y-%m-%d").date(),
                check_out_date=datetime.strptime(check_out, "%Y-%m-%d").date(),
                room_count=1,
                idempotency_key=key,
            ),
            self.guest,
        )

    def occupied(self, day: str) -> int:
        """读某日占用量（直接查库，不信应用层返回值）。"""
        row = self.conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ? AND stay_date = ?",
            (self.fix["room_type_id"], day),
        ).fetchone()
        return int(row["occupied_rooms"])

    def count(self, sql: str) -> int:
        """取单值计数。"""
        return int(self.conn.execute(sql).fetchone()[0])


class OrderLifecycleTest(FlowTestBase):
    """链路一：下单 → 酒店确认 → 入住 → 退房。"""

    def test_下单确认入住退房全链路(self) -> None:
        booking = self.place()

        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertEqual(booking.total_price_cents, 60000)  # 30000×2 晚
        self.assertEqual(len(booking.nights), 2)
        self.assertEqual(self.occupied("2027-03-01"), 1)
        self.assertEqual(self.occupied("2027-03-02"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM booking"), 1)

        booking = self.service.apply_event(booking.booking_no, BookingEvent.CONFIRM, self.staff)
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)

        booking = self.service.apply_event(booking.booking_no, BookingEvent.CHECK_IN, self.staff)
        self.assertEqual(booking.status, BookingStatus.CHECKED_IN)

        booking = self.service.apply_event(booking.booking_no, BookingEvent.CHECK_OUT, self.staff)
        self.assertEqual(booking.status, BookingStatus.CHECKED_OUT)

        self.assertEqual(self.count("SELECT COUNT(*) FROM stay_record"), 2)
        actions = [
            row["action"]
            for row in self.conn.execute(
                "SELECT action FROM stay_record ORDER BY id"
            ).fetchall()
        ]
        self.assertEqual(actions, ["CHECK_IN", "CHECK_OUT"])
        # 住过店的房不会因为退房就"还回来"：库存占用保持
        self.assertEqual(self.occupied("2027-03-01"), 1)

    def test_全链路留下完整审计(self) -> None:
        booking = self.place()
        self.service.apply_event(booking.booking_no, BookingEvent.CONFIRM, self.staff)
        self.service.apply_event(booking.booking_no, BookingEvent.CHECK_IN, self.staff)

        actions = [
            row["action"]
            for row in self.conn.execute(
                "SELECT action FROM audit_log WHERE target_id = ? ORDER BY id",
                (booking.booking_no,),
            ).fetchall()
        ]
        self.assertEqual(actions, ["CREATE", "CONFIRM", "CHECK_IN"])

        last = self.conn.execute(
            "SELECT before_state, after_state, operator_role FROM audit_log"
            " WHERE target_id = ? ORDER BY id DESC LIMIT 1",
            (booking.booking_no,),
        ).fetchone()
        self.assertEqual(last["before_state"], "CONFIRMED")
        self.assertEqual(last["after_state"], "CHECKED_IN")
        self.assertEqual(last["operator_role"], "HOTEL")


class RescheduleFlowTest(FlowTestBase):
    """链路二：改期（先占新、后放旧）。"""

    def test_改期链路旧日期释放新日期占用(self) -> None:
        booking = self.place("2027-03-01", "2027-03-03")
        self.service.apply_event(booking.booking_no, BookingEvent.CONFIRM, self.staff)

        moved = self.service.reschedule_booking(
            booking.booking_no,
            RescheduleCommand(
                new_check_in_date=datetime(2027, 3, 4).date(),
                new_check_out_date=datetime(2027, 3, 6).date(),
                reason="行程调整",
            ),
            self.guest,
        )

        self.assertEqual(moved.check_in_date, datetime(2027, 3, 4).date())
        self.assertEqual(moved.check_out_date, datetime(2027, 3, 6).date())
        self.assertEqual(moved.total_price_cents, 60000)
        self.assertEqual(len(moved.nights), 2)
        self.assertEqual(self.occupied("2027-03-01"), 0)
        self.assertEqual(self.occupied("2027-03-02"), 0)
        self.assertEqual(self.occupied("2027-03-04"), 1)
        self.assertEqual(self.occupied("2027-03-05"), 1)

    def test_改期到重叠区间只占用新增的那几天(self) -> None:
        booking = self.place("2027-03-01", "2027-03-03")
        self.service.apply_event(booking.booking_no, BookingEvent.CONFIRM, self.staff)

        moved = self.service.reschedule_booking(
            booking.booking_no,
            RescheduleCommand(
                new_check_in_date=datetime(2027, 3, 2).date(),
                new_check_out_date=datetime(2027, 3, 4).date(),
            ),
            self.guest,
        )

        self.assertEqual(moved.check_in_date, datetime(2027, 3, 2).date())
        # 03-02 本来就被本单占着（不该变成 2），03-01 释放，03-03 新增
        self.assertEqual(self.occupied("2027-03-01"), 0)
        self.assertEqual(self.occupied("2027-03-02"), 1)
        self.assertEqual(self.occupied("2027-03-03"), 1)

    def test_待确认订单不能改期(self) -> None:
        booking = self.place("2027-03-01", "2027-03-03")
        with self.assertRaises(ConflictError) as ctx:
            self.service.reschedule_booking(
                booking.booking_no,
                RescheduleCommand(
                    new_check_in_date=datetime(2027, 3, 4).date(),
                    new_check_out_date=datetime(2027, 3, 5).date(),
                ),
                self.guest,
            )
        self.assertEqual(ctx.exception.code, "CONFLICT")


class CancelFlowTest(FlowTestBase):
    """链路三：顾客取消已确认订单。"""

    def test_顾客取消链路释放库存并留审计(self) -> None:
        booking = self.place("2027-03-01", "2027-03-03")
        self.service.apply_event(booking.booking_no, BookingEvent.CONFIRM, self.staff)

        cancelled = self.service.cancel_booking(booking.booking_no, self.guest, "临时有事")

        self.assertEqual(cancelled.status, BookingStatus.CANCELLED)
        self.assertEqual(cancelled.cancel_reason, "临时有事")
        self.assertEqual(cancelled.cancel_initiator, "CUSTOMER")
        self.assertEqual(self.occupied("2027-03-01"), 0)
        self.assertEqual(self.occupied("2027-03-02"), 0)

        audit = self.conn.execute(
            "SELECT before_state, after_state FROM audit_log WHERE target_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (booking.booking_no,),
        ).fetchone()
        self.assertEqual(audit["before_state"], "CONFIRMED")
        self.assertEqual(audit["after_state"], "CANCELLED")

    def test_取消后同顾客可以重新预订同一时段(self) -> None:
        first = self.place("2027-03-01", "2027-03-02")
        self.service.apply_event(first.booking_no, BookingEvent.CONFIRM, self.staff)
        self.service.cancel_booking(first.booking_no, self.guest, "改主意")

        again = self.place("2027-03-01", "2027-03-02")
        self.assertEqual(again.status, BookingStatus.PENDING)
        self.assertEqual(self.count("SELECT COUNT(*) FROM booking"), 2)


class OverlapReviewTest(FlowTestBase):
    """U6 只拦"起止日完全相同"，重叠区间必须靠应用层在事务内复核。"""

    def test_重叠区间被应用层复核拒绝(self) -> None:
        self.place("2027-03-01", "2027-03-03")
        with self.assertRaises(DuplicateBookingError) as ctx:
            self.place("2027-03-02", "2027-03-04")

        self.assertEqual(ctx.exception.code, "DUPLICATE_BOOKING")
        self.assertEqual(ctx.exception.http_status, 409)
        self.assertEqual(self.count("SELECT COUNT(*) FROM booking"), 1)

    def test_首尾相接不算重叠(self) -> None:
        self.place("2027-03-01", "2027-03-03")
        second = self.place("2027-03-03", "2027-03-05")
        self.assertEqual(second.status, BookingStatus.PENDING)
        self.assertEqual(self.count("SELECT COUNT(*) FROM booking"), 2)


if __name__ == "__main__":
    unittest.main()
