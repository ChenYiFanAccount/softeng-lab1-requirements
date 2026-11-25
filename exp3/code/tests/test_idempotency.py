"""S3-3：幂等键——同一键提交两次只能落一单、返回同一个订单号。

幂等键的意义：界面上的"提交"按钮被双击、或网络重连后客户端重发，用户只该
得到一张订单。判定放在 ``BEGIN IMMEDIATE`` 事务内的**最前面**，因此第二次
请求既不会重复占用库存，也不会因 U6 索引抛错。
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
# 用例名即命题（"同一幂等键提交两次只建一单"），docstring 会变成同义反复。

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import FrozenClock
from app.application.commands import PlaceBookingCommand
from app.domain.enums import ActorRole


class IdempotencyTest(unittest.TestCase):
    """同一幂等键重复提交的三种表现。"""

    def setUp(self) -> None:
        self._stack = ExitStack()
        self.conn, self.path = self._stack.enter_context(support.temp_database())
        self.fix = support.insert_fixture(self.conn)
        for day in ("2027-03-01", "2027-03-02", "2027-03-03", "2027-03-04", "2027-03-05"):
            support.insert_inventory(self.conn, self.fix["room_type_id"], day, 5)
        clock = FrozenClock(datetime(2026, 11, 25, 10, 0))
        self.service = BookingAppService(self.conn, clock=clock)
        self.guest = Actor(self.fix["guest_id"], ActorRole.CUSTOMER)

    def tearDown(self) -> None:
        self._stack.close()

    def submit(self, key: str | None, check_in: str = "2027-03-01",
               check_out: str = "2027-03-03"):
        """模拟"同一个提交动作被发了两次"里的**一次**。"""
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

    def count(self, sql: str) -> int:
        """取单值计数。"""
        return int(self.conn.execute(sql).fetchone()[0])

    def test_同一幂等键提交两次只建一单(self) -> None:
        first = self.submit("idem-key-001")
        second = self.submit("idem-key-001")

        self.assertEqual(first.booking_no, second.booking_no)
        self.assertEqual(self.count("SELECT COUNT(*) FROM booking"), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM booking_night"), 2)
        self.assertEqual(self.count("SELECT COUNT(*) FROM idempotency_key"), 1)

    def test_幂等命中时不再重复占用库存(self) -> None:
        self.submit("idem-key-002")
        self.submit("idem-key-002")

        for day in ("2027-03-01", "2027-03-02"):
            occupied = int(
                self.conn.execute(
                    "SELECT occupied_rooms FROM room_inventory"
                    " WHERE room_type_id = ? AND stay_date = ?",
                    (self.fix["room_type_id"], day),
                ).fetchone()["occupied_rooms"]
            )
            self.assertEqual(occupied, 1, f"{day} 被重复占用了")

    def test_幂等命中不重复写审计(self) -> None:
        self.submit("idem-key-003")
        self.submit("idem-key-003")
        self.assertEqual(
            self.count("SELECT COUNT(*) FROM audit_log WHERE action = 'CREATE'"), 1
        )

    def test_不同幂等键是两张独立订单(self) -> None:
        first = self.submit("idem-key-004")
        second = self.submit("idem-key-005", "2027-03-03", "2027-03-05")
        self.assertNotEqual(first.booking_no, second.booking_no)
        self.assertEqual(self.count("SELECT COUNT(*) FROM booking"), 2)


if __name__ == "__main__":
    unittest.main()
