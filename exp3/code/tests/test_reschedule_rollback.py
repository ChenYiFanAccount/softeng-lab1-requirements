"""S3-4：改期失败必须整单回滚——新日期的占用一行都不能留下。

改期是"先占新、后放旧"，中途失败最危险的后果是"新房占了、老房没放"，
用户凭空多占一间房。这里两条路都钉住：

1. **预检就失败**：新日期余量不足，一行都不该改；
2. **写到一半失败**：第一次 ``add_occupied`` 成功、第二次抛异常，靠事务回滚把
   第一次的写入也抹掉（这条才真正验证 ``immediate_transaction`` 的回滚）。
"""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import ExitStack
from datetime import datetime
from unittest import mock

try:  # 两种跑法见 support.py
    from code.tests import support
except ImportError:  # pragma: no cover - discover 模式
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring
# 用例名即命题（"预检失败时旧日期占用不变"），docstring 只会重复它。

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import FrozenClock
from app.application.commands import PlaceBookingCommand, RescheduleCommand
from app.domain.enums import ActorRole, BookingEvent
from app.domain.errors import NoAvailabilityError
from app.infrastructure.db.inventory_repository import SqliteInventoryRepository


class RescheduleRollbackTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """改期失败时"库存 + 订单"必须一起退回原状。"""

    def setUp(self) -> None:
        self._stack = ExitStack()
        self.conn, self.path = self._stack.enter_context(support.temp_database())
        self.fix = support.insert_fixture(self.conn)
        # 旧区间 03-01..03-03 各 5 间；新区间 03-05..03-07 里 03-06 故意占满
        for day in ("2027-03-01", "2027-03-02", "2027-03-05", "2027-03-07", "2027-03-08"):
            support.insert_inventory(self.conn, self.fix["room_type_id"], day, 5)
        support.insert_inventory(self.conn, self.fix["room_type_id"], "2027-03-06", 1, occupied=1)
        clock = FrozenClock(datetime(2026, 11, 25, 11, 0))
        self.service = BookingAppService(self.conn, clock=clock)
        self.guest = Actor(self.fix["guest_id"], ActorRole.CUSTOMER)
        self.staff = Actor(
            self.fix["staff_id"], ActorRole.HOTEL_STAFF, hotel_id=self.fix["hotel_id"]
        )
        self.booking = self.service.place_booking(
            PlaceBookingCommand(
                guest_id=self.fix["guest_id"],
                hotel_id=self.fix["hotel_id"],
                room_type_id=self.fix["room_type_id"],
                check_in_date=datetime(2027, 3, 1).date(),
                check_out_date=datetime(2027, 3, 3).date(),
                room_count=1,
            ),
            self.guest,
        )
        self.service.apply_event(self.booking.booking_no, BookingEvent.CONFIRM, self.staff)

    def tearDown(self) -> None:
        self._stack.close()

    # ---------------------------------------------------------------- 工具

    def occupied(self, day: str) -> int:
        """读某日占用量。"""
        row = self.conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ? AND stay_date = ?",
            (self.fix["room_type_id"], day),
        ).fetchone()
        return int(row["occupied_rooms"])

    def move(self, check_in: str, check_out: str) -> None:
        """发起一次改期（不求成功，异常由用例捕获）。"""
        self.service.reschedule_booking(
            self.booking.booking_no,
            RescheduleCommand(
                new_check_in_date=datetime.strptime(check_in, "%Y-%m-%d").date(),
                new_check_out_date=datetime.strptime(check_out, "%Y-%m-%d").date(),
            ),
            self.guest,
        )

    def reload(self):
        """从库里重读订单，确认它没被改过。"""
        return self.service.get_booking(self.booking.booking_no, self.guest)

    # ---------------------------------------------------------------- 用例

    def test_新日期余量不足时新日期仍为零占用(self) -> None:
        with self.assertRaises(NoAvailabilityError) as ctx:
            self.move("2027-03-05", "2027-03-07")

        self.assertEqual(ctx.exception.code, "NO_AVAILABILITY")
        self.assertEqual(self.occupied("2027-03-05"), 0)
        self.assertEqual(self.occupied("2027-03-06"), 1)  # 本来就被别人占着

    def test_预检失败时旧日期占用不变(self) -> None:
        with self.assertRaises(NoAvailabilityError):
            self.move("2027-03-05", "2027-03-07")

        self.assertEqual(self.occupied("2027-03-01"), 1)
        self.assertEqual(self.occupied("2027-03-02"), 1)

    def test_预检失败时订单本身不变(self) -> None:
        before = self.reload()
        with self.assertRaises(NoAvailabilityError):
            self.move("2027-03-05", "2027-03-07")
        after = self.reload()

        self.assertEqual(after.check_in_date, before.check_in_date)
        self.assertEqual(after.check_out_date, before.check_out_date)
        self.assertEqual(after.total_price_cents, before.total_price_cents)

    def test_写到一半失败也整单回滚(self) -> None:
        original = SqliteInventoryRepository.add_occupied
        calls = {"count": 0}

        def flaky(repo, room_type_id, stay_date, delta):
            """第二次写库存时模拟数据库故障。"""
            calls["count"] += 1
            if calls["count"] == 2:
                raise sqlite3.OperationalError("磁盘 I/O 错误（模拟）")
            return original(repo, room_type_id, stay_date, delta)

        with mock.patch.object(SqliteInventoryRepository, "add_occupied", flaky):
            with self.assertRaises(sqlite3.OperationalError):
                self.move("2027-03-07", "2027-03-09")

        # 第一次 add_occupied 已经 +1，回滚后必须变回 0
        self.assertEqual(self.occupied("2027-03-07"), 0)
        self.assertEqual(self.occupied("2027-03-08"), 0)
        self.assertEqual(self.occupied("2027-03-01"), 1)
        self.assertEqual(self.reload().check_in_date, datetime(2027, 3, 1).date())


if __name__ == "__main__":
    unittest.main()
