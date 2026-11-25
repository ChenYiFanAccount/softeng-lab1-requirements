"""S4-3：no-show 判定落在**当地墙钟**的 23:59，而不是 UTC 的 23:59。

no-show 的判据是"入住日当天、过了 23:59、仍是已确认"，于是真正的边界在日期切换
的那一秒：

- 23:59 之前 → 还不能判 no-show，订单保持已确认（酒店还有机会办入住）；
- 过了 23:59（同一日期） → 记 no-show 并释放占用；
- **跨过零点**（次日 00:05，酒店仍没办入住） → 走的是 T5 自动入住而不是 T7：
  房间已经空置一晚，再判 no-show 就与"已确认且入住日已过"的兜底规则打了架。

时钟给的是 **UTC**（``SystemClock`` 与 ``FrozenClock`` 都是），而 ``check_in_date``
与 ``no_show_cutoff`` 都是**本地日历/墙钟**，所以本文件的每个时刻都先用
``local_at()`` 换算成 UTC 再喂时钟——这本身就是 S4-R1-01 的回归手段：
若哪天又拿 UTC 直接比 23:59，``test_UTC时刻的2359不会被当成当日未入住`` 会立刻红。

全部时刻都是假的，不涉及任何真实等待。
"""

from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
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
from app.application.clock import FrozenClock, SystemClock
from app.application.commands import PlaceBookingCommand
from app.application.fulfillment_service import FulfillmentService
from app.domain.enums import ActorRole, BookingEvent, BookingStatus

#: 入住日与退房日（单晚，便于观察首晚占用）
CHECK_IN = "2027-03-01"
CHECK_OUT = "2027-03-02"

#: 建单时刻：入住日前一天上午（UTC，与展示时区无关）
CREATED_AT = datetime(2027, 2, 28, 9, 0, 0)

#: 本地时区固定偏移：Asia/Shanghai 不实行夏令时，+08:00 与 ZoneInfo 完全等价，
#: 用固定偏移可以避免测试机缺 tzdata 时 ZoneInfo 抛异常。
LOCAL_OFFSET = timezone(timedelta(hours=8))


def local_at(*parts: int) -> datetime:
    """本地墙钟时间 → 时钟使用的 UTC 朴素时刻。

    Args:
        *parts: ``datetime`` 的位置参数（年、月、日、时、分、秒）。

    Returns:
        换成 UTC 后去掉 tzinfo 的时刻，可直接喂 ``FrozenClock``。
    """
    return datetime(*parts, tzinfo=LOCAL_OFFSET).astimezone(timezone.utc).replace(tzinfo=None)


class NoShowClockTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """23:59 这条线两侧各一条用例，并钉住"UTC 与本地差八小时"这个坑。"""

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

    def scan_with(self, moment: datetime, settings: dict | None = None):
        """把时钟拨到 ``moment`` 后跑一轮扫描。

        传入自定义 ``settings`` 时会新建一个服务：时区是配置项，必须能换。
        """
        self.clock.set(moment)
        service = self.fulfillment
        if settings is not None:
            service = FulfillmentService(self.conn, clock=self.clock, settings=settings)
        return service.scan_once()

    # ---------------------------------------------------------------- 用例

    def test_本地2358仍然算已确认不判未入住(self) -> None:
        report = self.scan_with(local_at(2027, 3, 1, 23, 58, 0))

        self.assertEqual(report.no_shows, 0)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.CONFIRMED)
        self.assertEqual(self.occupied(), 1)

    def test_本地2359之后记为未入住并释放占用(self) -> None:
        report = self.scan_with(local_at(2027, 3, 1, 23, 59, 30))

        self.assertEqual(report.no_shows, 1)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.NO_SHOW)
        self.assertEqual(self.occupied(), 0)

    def test_UTC时刻的2359不会被当成当日未入住(self) -> None:
        # 朴素 23:59:30 按 UTC 解释 = 本地次日 07:59:30：入住日已过，应走 T5，
        # 绝不能因为"时分看起来过了 23:59"就记当日 no-show（S4-R1-01 的回归锚点）。
        report = self.scan_with(datetime(2027, 3, 1, 23, 59, 30))

        self.assertEqual(report.no_shows, 0)
        self.assertEqual(report.auto_check_ins, 1)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.CHECKED_IN)

    def test_跨过零点后走自动入住而不是未入住(self) -> None:
        report = self.scan_with(local_at(2027, 3, 2, 0, 5, 0))

        self.assertEqual(report.auto_check_ins, 1)
        self.assertEqual(report.no_shows, 0)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.CHECKED_IN)
        self.assertEqual(self.occupied(), 1)

    def test_未入住判定不受提前一天影响(self) -> None:
        report = self.scan_with(local_at(2027, 2, 28, 23, 59, 30))

        self.assertEqual(report.no_shows, 0)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.CONFIRMED)

    def test_未入住后再扫描不会重复处理(self) -> None:
        self.scan_with(local_at(2027, 3, 1, 23, 59, 30))
        self.clock.advance(timedelta(minutes=2))

        second = self.fulfillment.scan_once()

        self.assertEqual(second.no_shows, 0)
        self.assertEqual(second.total, 0)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.NO_SHOW)

    def test_cutoff随时区配置平移(self) -> None:
        # 把时区配成 UTC，则本地墙钟就是 UTC：同一时刻要判 no-show。
        settings = {"runtime": {"timezone": "UTC"}}

        report = self.scan_with(datetime(2027, 3, 1, 23, 59, 30), settings=settings)

        self.assertEqual(report.no_shows, 1)
        self.assertIs(self.status_of(self.booking_no), BookingStatus.NO_SHOW)

    def test_扫描报告同时给出UTC与本地时刻(self) -> None:
        report = self.scan_with(local_at(2027, 3, 1, 10, 0, 0))

        payload = report.to_dict()

        self.assertEqual(payload["scanned_at"], "2027-03-01 02:00:00")
        self.assertEqual(payload["scanned_at_local"], "2027-03-01 10:00:00")
        self.assertEqual(payload["timezone"], "Asia/Shanghai")

    def test_时钟自带来源标签(self) -> None:
        """真实时钟与假时钟要能自证来源，报告里才分得清"真发生"与"用例拨动"。"""
        real = SystemClock()
        self.assertEqual(real.source(), "system")
        self.assertIsNotNone(real.now().tzinfo)

        frozen = FrozenClock(current=local_at(2027, 3, 1, 10, 0, 0))
        self.assertEqual(frozen.source(), "frozen")
        self.assertEqual(frozen.now(), local_at(2027, 3, 1, 10, 0, 0))


if __name__ == "__main__":
    unittest.main()
