"""S4-1 / S4-2：超时取消扫描，且必须用假时钟（禁止真实休眠）。

判据有两半：功能对（超时单被 T3 取消、库存回补）＋ 手法对（不靠真实等待）。
因此本文件里的时间全部来自 ``FrozenClock``：``advance()`` 一步把"31 分钟后"拨过去，
扫描是同步调用，整套用例应在毫秒级跑完（证据里的"总耗时 < 5s"由此而来）。

S4-2 单独钉一条：**重复扫描不重复回补**——第一次扫描把订单改成已取消之后，
第二次扫描的三条查询都查不到它，占用不会再降、审计也不再新增。
"""

from __future__ import annotations

import sys
import time
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
# 用例名即命题，再补 docstring 等于把同一句话写两遍（同 S2/S3 的取舍）。

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import FrozenClock
from app.application.commands import PlaceBookingCommand
from app.application.fulfillment_service import FulfillmentService
from app.domain.enums import ActorRole, BookingStatus

#: 夹具覆盖的住宿日期
STAY_DATES = ("2027-03-01", "2027-03-02", "2027-03-03", "2027-03-04")

#: 建单时刻：入住日之前，且不落在任何整点边界上，便于观察分钟级推进
CREATED_AT = datetime(2027, 2, 28, 10, 0, 0)

#: 本模块开始执行的时刻：用于把"整套扫描用例没有真实等待"变成**可断言的输出**
_STARTED_AT = time.perf_counter()


def tearDownModule() -> None:
    """打印并断言整套用例的总耗时（S4-1：必须 < 5s）。

    真等待一旦被引入（哪怕只等 30 分钟超时一次），这里的断言会立刻失败；
    把阈值写进代码而不是写进交付说明，是为了让判据自己会叫。
    """
    elapsed_ms = int((time.perf_counter() - _STARTED_AT) * 1000)
    print(f"elapsed_total_ms={elapsed_ms}")
    assert elapsed_ms < 5000, f"扫描用例总耗时 {elapsed_ms}ms 超过 5s，说明引入了真实等待"
    print("assert_elapsed_lt_5s=True")


class TimeoutScanTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """超时取消：假时钟推进 → 扫描 → 状态与库存同时收敛。"""

    def setUp(self) -> None:
        self._stack = ExitStack()
        self.conn, self.path = self._stack.enter_context(support.temp_database())
        self.fix = support.insert_fixture(self.conn)
        for day in STAY_DATES:
            support.insert_inventory(self.conn, self.fix["room_type_id"], day, 5)
        self.clock = FrozenClock(CREATED_AT)
        self.bookings = BookingAppService(self.conn, clock=self.clock)
        self.fulfillment = FulfillmentService(self.conn, clock=self.clock)
        self.guest = Actor(self.fix["guest_id"], ActorRole.CUSTOMER, login_name="13900000001")

    def tearDown(self) -> None:
        self._stack.close()

    # ---------------------------------------------------------------- 工具

    def place(self, check_in: str = "2027-03-01", check_out: str = "2027-03-03"):
        """以顾客身份下一张待确认单。"""
        return self.bookings.place_booking(
            PlaceBookingCommand(
                guest_id=self.fix["guest_id"],
                hotel_id=self.fix["hotel_id"],
                room_type_id=self.fix["room_type_id"],
                check_in_date=datetime.strptime(check_in, "%Y-%m-%d").date(),
                check_out_date=datetime.strptime(check_out, "%Y-%m-%d").date(),
                room_count=1,
            ),
            self.guest,
        )

    def occupied(self, day: str) -> int:
        """某日占用量（直接查库）。"""
        row = self.conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ? AND stay_date = ?",
            (self.fix["room_type_id"], day),
        ).fetchone()
        return int(row["occupied_rooms"])

    def audit_actions(self) -> list[str]:
        """审计动作序列（新→旧）。"""
        rows = self.conn.execute("SELECT action FROM audit_log ORDER BY id DESC").fetchall()
        return [str(row["action"]) for row in rows]

    # ---------------------------------------------------------------- 用例

    def test_超时31分钟后扫描取消订单并回补库存(self) -> None:
        booking = self.place()
        self.assertEqual(self.occupied("2027-03-01"), 1)
        self.clock.advance(timedelta(minutes=31))

        report = self.fulfillment.scan_once()

        self.assertEqual(report.timeouts, 1)
        reloaded = self.bookings.get_booking(booking.booking_no, self.guest)
        self.assertIs(reloaded.status, BookingStatus.CANCELLED)
        self.assertEqual(self.occupied("2027-03-01"), 0)
        self.assertEqual(self.occupied("2027-03-02"), 0)
        self.assertIn("TIMEOUT", self.audit_actions())

    def test_未超时的待确认订单不会被扫描动到(self) -> None:
        booking = self.place()
        self.clock.advance(timedelta(minutes=29))

        report = self.fulfillment.scan_once()

        self.assertEqual(report.total, 0)
        reloaded = self.bookings.get_booking(booking.booking_no, self.guest)
        self.assertIs(reloaded.status, BookingStatus.PENDING)
        self.assertEqual(self.occupied("2027-03-01"), 1)

    def test_重复扫描不重复回补库存(self) -> None:
        booking = self.place()
        self.clock.advance(timedelta(minutes=31))
        self.fulfillment.scan_once()
        occupied_after_first = self.occupied("2027-03-01")
        audit_after_first = len(self.audit_actions())

        second = self.fulfillment.scan_once()

        self.assertEqual(second.total, 0)
        self.assertEqual(self.occupied("2027-03-01"), occupied_after_first)
        self.assertEqual(self.occupied("2027-03-02"), occupied_after_first)
        self.assertEqual(len(self.audit_actions()), audit_after_first)
        self.assertIs(
            self.bookings.get_booking(booking.booking_no, self.guest).status,
            BookingStatus.CANCELLED,
        )

    def test_一轮扫描处理多张超时单(self) -> None:
        pairs = [
            ("2027-03-01", "2027-03-02"),
            ("2027-03-02", "2027-03-03"),
            ("2027-03-03", "2027-03-04"),
        ]
        for check_in, check_out in pairs:
            self.place(check_in, check_out)
        self.clock.advance(timedelta(minutes=40))

        report = self.fulfillment.scan_once()

        self.assertEqual(report.timeouts, 3)
        for day in ("2027-03-01", "2027-03-02", "2027-03-03"):
            self.assertEqual(self.occupied(day), 0)

    def test_扫描推进三天跨度也不靠真实等待(self) -> None:
        booking = self.place()
        self.clock.advance(timedelta(days=3, minutes=5))

        started = time.perf_counter()
        report = self.fulfillment.scan_once()
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 1.0)
        self.assertEqual(report.total, 1)
        self.assertIs(
            self.bookings.get_booking(booking.booking_no, self.guest).status,
            BookingStatus.CANCELLED,
        )


if __name__ == "__main__":
    unittest.main()
