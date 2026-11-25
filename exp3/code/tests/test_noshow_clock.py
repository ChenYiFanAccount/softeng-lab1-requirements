"""S4-3：no-show 判定跨零点（23:59 前后两态各 1 例）。

no-show 的判据是"入住日当天、过了 23:59、仍是已确认"，于是真正的边界在日期切换
的那一秒：

- 23:59 之前 → 还不能判 no-show，订单保持已确认（酒店还有机会办入住）；
- 过了 23:59（同一日期） → 记 no-show 并释放占用；
- **跨过零点**（次日 00:05，酒店仍没办入住） → 走的是 T5 自动入住而不是 T7：
  房间已经空置一晚，再判 no-show 就与"已确认且入住日已过"的兜底规则打了架。

两态各一条用例，时钟都是假的，不涉及任何真实等待。
"""

from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:  # 两种跑法都要成立（G2-R1-02）
    sys.path.insert(0, str(_CODE_ROOT))

try:  # 两种跑法：`-m unittest code.tests.x` 与 `discover -s code/tests -t code`
    from code.tests import support
except ImportError:  # pragma: no cover - discover 模式
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import FrozenClock
from app.application.commands import PlaceBookingCommand
from app.application.fulfillment_service import FulfillmentService
from app.domain.enums import ActorRole, BookingEvent, BookingStatus

#: 入住日与退房日（单晚，便于观察首晚占用）
CHECK_IN = "2027-03-01"
CHECK_OUT = "2027-03-02"

#: 建单时刻：入住日前一天上午
CREATED_AT = datetime(2027, 2, 28, 9, 0, 0)


class NoShowClockTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """23:59 这条线两侧各一条用例。"""

    def setUp(self) -> None:
        self._stack = ExitStack()
        self.conn, self.path = self._stack.enter_context(support.temp_database())
        self.fix = support.insert_fixture(self.conn)
        support.insert_inventory(self.conn, self.fix["room_type_id"], CHECK_IN, 5)
        self.clock = FrozenClock(CREATED_AT)
        self.bookings = BookingAppService(self.conn, clock=self.clock)
        self.fulfillment = FulfillmentService(self.conn, clock=self.clock)
        self.guest = Actor(self.fix["guest_id"], ActorRole.CUSTOMER, login_name="13900000001")
        self.staff = Actor(
            self.fix["staff_id"],
            ActorRole.HOTEL_STAFF,
            hotel_id=self.fix["hotel_id"],
            login_name="13900000002",
        )
        self.booking_no = self._confirmed_booking()

    def tearDown(self) -> None:
        self._stack.close()

    # ---------------------------------------------------------------- 工具

    def _confirmed_booking(self) -> str:
        """下一单并由酒店确认，返回订单号。"""
        booking = self.bookings.place_booking(
            PlaceBookingCommand(
                guest_id=self.fix["guest_id"],
                hotel_id=self.fix["hotel_id"],
                room_type_id=self.fix["room_type_id"],
                check_in_date=datetime.strptime(CHECK_IN, "%Y-%m-%d").date(),
                check_out_date=datetime.strptime(CHECK_OUT, "%Y-%m-%d").date(),
                room_count=1,
            ),
            self.guest,
        )
        self.bookings.apply_event(booking.booking_no, BookingEvent.CONFIRM, self.staff)
        return booking.booking_no

    def occupied(self) -> int:
        """首晚占用量（直接查库）。"""
        row = self.conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ? AND stay_date = ?",
            (self.fix["room_type_id"], CHECK_IN),
        ).fetchone()
        return int(row["occupied_rooms"])

    def status_of(self, booking_no: str) -> BookingStatus:
        """订单当前状态。"""
        return self.bookings.get_booking(booking_no, self.guest).status

    # ---------------------------------------------------------------- 用例

    def test_入住日2358仍然算已确认不判未入住(self) -> None:
        self.clock.set(datetime(2027, 3, 1, 23, 58, 0))

        report = self.fulfillment.scan_once()

        self.assertEqual(report.no_shows, 0)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.CONFIRMED)
        self.assertEqual(self.occupied(), 1)

    def test_入住日2359之后记为未入住并释放占用(self) -> None:
        self.clock.set(datetime(2027, 3, 1, 23, 59, 30))

        report = self.fulfillment.scan_once()

        self.assertEqual(report.no_shows, 1)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.NO_SHOW)
        self.assertEqual(self.occupied(), 0)

    def test_跨过零点后走自动入住而不是未入住(self) -> None:
        self.clock.set(datetime(2027, 3, 2, 0, 5, 0))

        report = self.fulfillment.scan_once()

        self.assertEqual(report.auto_check_ins, 1)
        self.assertEqual(report.no_shows, 0)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.CHECKED_IN)
        self.assertEqual(self.occupied(), 1)

    def test_未入住判定不受提前一天影响(self) -> None:
        self.clock.set(datetime(2027, 2, 28, 23, 59, 30))

        report = self.fulfillment.scan_once()

        self.assertEqual(report.no_shows, 0)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.CONFIRMED)

    def test_未入住后再扫描不会重复处理(self) -> None:
        self.clock.set(datetime(2027, 3, 1, 23, 59, 30))
        self.fulfillment.scan_once()
        self.clock.advance(timedelta(minutes=2))

        second = self.fulfillment.scan_once()

        self.assertEqual(second.no_shows, 0)
        self.assertEqual(second.total, 0)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.NO_SHOW)


if __name__ == "__main__":
    unittest.main()
