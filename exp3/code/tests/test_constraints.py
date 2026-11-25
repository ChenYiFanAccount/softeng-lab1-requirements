"""约束层防护（S1-7）：非法数据必须在数据库边界就被挡住，而不是靠界面自觉。

四条硬约束各一条用例：负库存、退房日 ≤ 入住日、``(房型, 日期)`` 重复、有效订单
重复预订（部分唯一索引）。另加外键与「取消后可重订」两条回归，防止把 U6 写成
"永久锁死同一时段"。
"""

from __future__ import annotations

import contextlib
import sqlite3
import unittest

try:  # 跑法一：python -m unittest code.tests.test_x
    from code.tests import support
except ImportError:  # pragma: no cover - 跑法二：discover -s code/tests -t code
    import support  # type: ignore[no-redef]


class ConstraintTest(unittest.TestCase):
    """CHECK / UNIQUE / 部分唯一索引 / 外键的行为契约。"""

    def setUp(self) -> None:
        self._stack = contextlib.ExitStack()
        self.conn, _ = self._stack.enter_context(support.temp_database())
        self.fixture = support.insert_fixture(self.conn)
        support.insert_inventory(self.conn, self.fixture["room_type_id"], "2027-03-01", 5, 2)

    def tearDown(self) -> None:
        self._stack.close()

    def _book(
        self,
        booking_no: str,
        status: str,
        check_in: str = "2027-03-01",
        check_out: str = "2027-03-03",
    ) -> int:
        """插一张订单的短写法，避免每个用例重复六个位置参数。"""
        return support.insert_booking(
            self.conn, self.fixture, booking_no, check_in, check_out, status
        )

    def test_negative_available_rooms_rejected(self) -> None:
        """可售间数不能被改成负数（CHECK available_rooms >= 0）。"""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE room_inventory SET available_rooms = -1 WHERE room_type_id = ?",
                (self.fixture["room_type_id"],),
            )

    def test_occupied_over_available_rejected(self) -> None:
        """占用不得超过可售（行内区间约束），否则余量会变成负数。"""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE room_inventory SET occupied_rooms = 99 WHERE room_type_id = ?",
                (self.fixture["room_type_id"],),
            )

    def test_checkout_not_after_checkin_rejected(self) -> None:
        """退房日必须晚于入住日；相等或更早都被 CHECK 挡住。"""
        with self.assertRaises(sqlite3.IntegrityError):
            self._book("B-EQ", "PENDING", "2027-03-01", "2027-03-01")
        with self.assertRaises(sqlite3.IntegrityError):
            self._book("B-REV", "PENDING", "2027-03-05", "2027-03-02")

    def test_duplicate_room_date_rejected(self) -> None:
        """同一房型同一天只能有一行库存（U4）。"""
        with self.assertRaises(sqlite3.IntegrityError):
            support.insert_inventory(self.conn, self.fixture["room_type_id"], "2027-03-01", 5, 0)

    def test_duplicate_active_booking_rejected(self) -> None:
        """有效状态内，同顾客+同酒店+同房型+同时段只能有一单（U6 部分唯一索引）。"""
        self._book("B-1", "PENDING")
        with self.assertRaises(sqlite3.IntegrityError):
            self._book("B-2", "CONFIRMED")

    def test_cancelled_booking_does_not_block_new_one(self) -> None:
        """旧单取消后可重订同一时段——U6 只拦有效状态，否则顾客取消一次就永远订不了。"""
        self._book("B-OLD", "CANCELLED")
        booking_id = self._book("B-NEW", "PENDING")
        self.assertGreater(booking_id, 0)

    def test_overlapping_dates_are_not_blocked_by_index(self) -> None:
        """U6 的边界：起止日不同的重叠单索引拦不住，必须由应用层在事务内校验。"""
        self._book("B-OV1", "PENDING")
        booking_id = self._book("B-OV2", "PENDING", "2027-03-02", "2027-03-04")
        self.assertGreater(booking_id, 0)

    def test_foreign_key_violation_rejected(self) -> None:
        """外键真的生效：指向不存在的顾客必须失败（证明 PRAGMA foreign_keys=ON）。"""
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO booking (booking_no, guest_id, hotel_id, room_type_id,"
                " room_count, check_in_date, check_out_date, total_price_cents, status,"
                " created_at, updated_at) VALUES ('B-FK', 999999, ?, ?, 1,"
                " '2027-03-01', '2027-03-02', 100, 'PENDING',"
                " '2026-11-25 00:00:00', '2026-11-25 00:00:00')",
                (self.fixture["hotel_id"], self.fixture["room_type_id"]),
            )


if __name__ == "__main__":
    unittest.main()
