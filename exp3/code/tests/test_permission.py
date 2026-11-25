"""S3-5：越权一律 403，且"不存在"与"无权访问"必须返回同一错误码与同一文案。

后半条是安全要求而不是洁癖：如果两种情况文案不同（或一个 403、一个 404），
攻击者只要枚举订单号就能判断"哪些订单真实存在"，再配合撞库就能定位用户。

第二条线索是"角色不许做"与"看不见"也要分开表达：
- 看不见（跨酒店、别人家的订单）→ 统一蒙版 403；
- 看得见但角色不对（顾客想确认自己的单）→ 明确的 403 + 状态机拒绝理由。
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from datetime import datetime

try:  # 两种跑法见 support.py
    from code.tests import support
except ImportError:  # pragma: no cover - discover 模式
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring
# 用例名即命题；这个文件里"哪两种情况必须返回同一错误"正是靠名字表达的。

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import FrozenClock
from app.application.commands import PlaceBookingCommand
from app.application.errors import MASKED_BOOKING_MESSAGE
from app.domain.enums import ActorRole, BookingEvent, BookingStatus
from app.domain.errors import PermissionDeniedError

#: 一个肯定不存在的订单号
MISSING_NO = "BK00000000000000DEAD"


class PermissionTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """三类越权：跨顾客、跨酒店、跨角色。"""

    def setUp(self) -> None:
        self._stack = ExitStack()
        self.conn, self.path = self._stack.enter_context(support.temp_database())
        self.fix = support.insert_fixture(self.conn)
        self.other = self.insert_other_hotel()
        for day in ("2027-03-01", "2027-03-02", "2027-03-03"):
            support.insert_inventory(self.conn, self.fix["room_type_id"], day, 5)
        self.clock = FrozenClock(datetime(2026, 11, 25, 12, 0, 0))
        self.service = BookingAppService(self.conn, clock=self.clock)
        self.guest = Actor(self.fix["guest_id"], ActorRole.CUSTOMER, login_name="13900000001")
        self.other_guest = Actor(
            self.other["guest_id"], ActorRole.CUSTOMER, login_name="13900000009"
        )
        self.staff = Actor(
            self.fix["staff_id"], ActorRole.HOTEL_STAFF, hotel_id=self.fix["hotel_id"]
        )
        self.other_staff = Actor(
            self.other["staff_id"], ActorRole.HOTEL_STAFF, hotel_id=self.other["hotel_id"]
        )
        self.admin = Actor(self.other["admin_id"], ActorRole.PLATFORM_ADMIN)
        self.booking = self.place(self.guest, self.fix["guest_id"])

    def tearDown(self) -> None:
        self._stack.close()

    # ---------------------------------------------------------------- 工具

    def insert_other_hotel(self) -> dict[str, int]:
        """插第二家酒店 + 它的店长 + 一名顾客 + 一名平台管理员。"""
        stamp = "2026-11-25 00:00:00"
        hotel_id = int(
            self.conn.execute(
                "INSERT INTO hotel (name, address, phone, audit_status, created_at)"
                " VALUES ('另一家酒店', '另一条路 2 号', '010-11111111', 'APPROVED', ?)",
                (stamp,),
            ).lastrowid
        )
        staff_id = int(
            self.conn.execute(
                "INSERT INTO user_account (login_name, password_hash, role, hotel_id, status,"
                " created_at) VALUES ('13900000008', 'x', 'HOTEL_STAFF', ?, 'ACTIVE', ?)",
                (hotel_id, stamp),
            ).lastrowid
        )
        guest_id = int(
            self.conn.execute(
                "INSERT INTO user_account (login_name, password_hash, role, hotel_id, status,"
                " created_at) VALUES ('13900000009', 'x', 'CUSTOMER', NULL, 'ACTIVE', ?)",
                (stamp,),
            ).lastrowid
        )
        admin_id = int(
            self.conn.execute(
                "INSERT INTO user_account (login_name, password_hash, role, hotel_id, status,"
                " created_at) VALUES ('13800000000', 'x', 'PLATFORM_ADMIN', NULL, 'ACTIVE', ?)",
                (stamp,),
            ).lastrowid
        )
        return {
            "hotel_id": hotel_id,
            "staff_id": staff_id,
            "guest_id": guest_id,
            "admin_id": admin_id,
        }

    def place(self, actor: Actor, guest_id: int):
        """以指定身份下一单。"""
        return self.service.place_booking(
            PlaceBookingCommand(
                guest_id=guest_id,
                hotel_id=self.fix["hotel_id"],
                room_type_id=self.fix["room_type_id"],
                check_in_date=datetime(2027, 3, 1).date(),
                check_out_date=datetime(2027, 3, 3).date(),
                room_count=1,
            ),
            actor,
        )

    def masked_error(self, booking_no: str, actor: Actor) -> PermissionDeniedError:
        """取一次"看不见"的错误，供比对。"""
        with self.assertRaises(PermissionDeniedError) as ctx:
            self.service.get_booking(booking_no, actor)
        return ctx.exception

    # ---------------------------------------------------------------- 用例

    def test_不存在与无权访问返回同一错误码与文案(self) -> None:
        missing = self.masked_error(MISSING_NO, self.other_guest)
        forbidden = self.masked_error(self.booking.booking_no, self.other_guest)

        self.assertEqual(missing.code, "PERMISSION_DENIED")
        self.assertEqual(forbidden.code, missing.code)
        self.assertEqual(str(forbidden), str(missing))
        self.assertEqual(forbidden.http_status, missing.http_status)
        self.assertEqual(str(missing), MASKED_BOOKING_MESSAGE)

    def test_跨酒店员工看到的是蒙版错误(self) -> None:
        error = self.masked_error(self.booking.booking_no, self.other_staff)
        self.assertEqual(error.code, "PERMISSION_DENIED")
        self.assertEqual(str(error), MASKED_BOOKING_MESSAGE)
        self.assertEqual(error.http_status, 403)

    def test_顾客不能确认自己的订单(self) -> None:
        with self.assertRaises(PermissionDeniedError) as ctx:
            self.service.apply_event(self.booking.booking_no, BookingEvent.CONFIRM, self.guest)

        self.assertEqual(ctx.exception.code, "PERMISSION_DENIED")
        self.assertNotEqual(str(ctx.exception), MASKED_BOOKING_MESSAGE)
        # 状态没变；审计多了一行 DENIED（S4-4：403 也要留痕，但订单本身不动）
        self.assertEqual(
            self.service.get_booking(self.booking.booking_no, self.guest).status,
            BookingStatus.PENDING,
        )
        rows = self.conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()
        self.assertEqual([str(row["action"]) for row in rows], ["CREATE", "DENIED:CONFIRM"])

    def test_跨酒店员工不能确认本店订单(self) -> None:
        with self.assertRaises(PermissionDeniedError) as ctx:
            self.service.apply_event(
                self.booking.booking_no, BookingEvent.CONFIRM, self.other_staff
            )
        self.assertEqual(str(ctx.exception), MASKED_BOOKING_MESSAGE)

    def test_本店员工可以确认订单(self) -> None:
        confirmed = self.service.apply_event(
            self.booking.booking_no, BookingEvent.CONFIRM, self.staff
        )
        self.assertEqual(confirmed.status, BookingStatus.CONFIRMED)

    def test_管理员可以跨酒店确认订单(self) -> None:
        confirmed = self.service.apply_event(
            self.booking.booking_no, BookingEvent.CONFIRM, self.admin
        )
        self.assertEqual(confirmed.status, BookingStatus.CONFIRMED)

    def test_顾客不能替别人下单(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.service.place_booking(
                PlaceBookingCommand(
                    guest_id=self.other["guest_id"],
                    hotel_id=self.fix["hotel_id"],
                    room_type_id=self.fix["room_type_id"],
                    check_in_date=datetime(2027, 3, 1).date(),
                    check_out_date=datetime(2027, 3, 2).date(),
                    room_count=1,
                ),
                self.guest,
            )


if __name__ == "__main__":
    unittest.main()
