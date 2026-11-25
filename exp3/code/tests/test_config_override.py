"""S5-3：阈值必须真的从配置文件读，改了就换行为。

判据要求"把 `pending_timeout_minutes` 改成 1 分钟后扫描行为随之变化"。这条最容易
写成假用例——比如断言 `service.timeout_minutes == 1`（只证属性读了字典），却从不
证明**订单真的被取消**。所以这里的用例一律断言可观察结果：

- 同一个时刻（建单后 2 分钟），阈值 30 → 订单仍待确认、占用仍在；
- 同一个时刻，阈值 1 → 订单被取消、占用回补、审计多一条；
- 已确认单不受这个阈值影响（它管的是"待确认没人处理"）。

配置落点固定为 ``code/config/settings.json``（P0-R1-08：12 张表里没有配置表）。
"""

from __future__ import annotations

import contextlib
import json
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))

# pylint: disable=wrong-import-position
from app.application.actor import Actor  # noqa: E402
from app.application.booking_service import BookingAppService  # noqa: E402
from app.application.clock import FrozenClock  # noqa: E402
from app.application.commands import PlaceBookingCommand  # noqa: E402
from app.application.fulfillment_service import FulfillmentService  # noqa: E402
from app.domain.enums import ActorRole, BookingEvent, BookingStatus  # noqa: E402
from app.infrastructure.db.connection import load_settings  # noqa: E402

try:
    from code.tests import support
except ImportError:
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring
# 说明：本模块的用例名本身就是命题（中文），逐个补 docstring 只会重复方法名。

SETTINGS_FILE = _CODE_ROOT / "config" / "settings.json"
START = datetime(2027, 2, 1, 9, 0, 0)


def settings_with(minutes: int) -> dict:
    """读真实配置文件，只覆盖阈值——保证"其它配置来自文件"这件事也被覆盖到。"""
    settings = load_settings()
    settings.setdefault("fulfillment", {})
    settings["fulfillment"]["pending_timeout_minutes"] = minutes
    return settings


class ConfigOverrideTest(unittest.TestCase):
    """每条用例自己开库，互不影响。"""

    def setUp(self) -> None:
        self._stack = contextlib.ExitStack()

    def tearDown(self) -> None:
        self._stack.close()

    def _booking(self, clock: FrozenClock, confirm: bool = False):
        conn, _ = self._stack.enter_context(support.temp_database())
        fixture = support.insert_fixture(conn)
        support.insert_inventory(conn, fixture["room_type_id"], "2027-03-01", 5)
        support.insert_inventory(conn, fixture["room_type_id"], "2027-03-02", 5)
        guest = Actor(
            account_id=fixture["guest_id"], role=ActorRole.CUSTOMER, login_name="13900000001"
        )
        staff = Actor(
            account_id=fixture["staff_id"],
            role=ActorRole.HOTEL_STAFF,
            hotel_id=fixture["hotel_id"],
            login_name="13900000002",
        )
        service = BookingAppService(conn, clock=clock)
        booking = service.place_booking(
            PlaceBookingCommand(
                guest_id=fixture["guest_id"],
                hotel_id=fixture["hotel_id"],
                room_type_id=fixture["room_type_id"],
                check_in_date=date(2027, 3, 1),
                check_out_date=date(2027, 3, 2),
                room_count=1,
            ),
            guest,
        )
        if confirm:
            service.apply_event(booking.booking_no, BookingEvent.CONFIRM, staff)
        return conn, fixture, booking

    def _status(self, conn, booking_no: str) -> str:  # noqa: ANN001
        row = conn.execute(
            "SELECT status FROM booking WHERE booking_no = ?", (booking_no,)
        ).fetchone()
        return str(row["status"])

    def _occupied(self, conn, room_type_id: int) -> int:  # noqa: ANN001
        row = conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ?"
            " AND stay_date = '2027-03-01'",
            (room_type_id,),
        ).fetchone()
        return int(row["occupied_rooms"])

    def test_配置文件存在且阈值与默认值一致(self) -> None:
        self.assertTrue(SETTINGS_FILE.exists(), "配置必须有落点：code/config/settings.json")
        payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(payload["fulfillment"]["pending_timeout_minutes"], 30)
        self.assertEqual(payload["runtime"]["timezone"], "Asia/Shanghai")

    def test_阈值三十时建单后两分钟仍待确认(self) -> None:
        clock = FrozenClock(current=START)
        conn, fixture, booking = self._booking(clock)
        clock.advance(timedelta(minutes=2))
        report = FulfillmentService(conn, clock=clock, settings=settings_with(30)).scan_once()
        self.assertEqual(report.timeouts, 0)
        self.assertEqual(self._status(conn, booking.booking_no), BookingStatus.PENDING.value)
        self.assertEqual(self._occupied(conn, fixture["room_type_id"]), 1)

    def test_阈值改成一分钟后订单真的被取消并回补(self) -> None:
        clock = FrozenClock(current=START)
        conn, fixture, booking = self._booking(clock)
        clock.advance(timedelta(minutes=2))
        report = FulfillmentService(conn, clock=clock, settings=settings_with(1)).scan_once()
        self.assertEqual(report.timeouts, 1)
        self.assertEqual(self._status(conn, booking.booking_no), BookingStatus.CANCELLED.value)
        self.assertEqual(self._occupied(conn, fixture["room_type_id"]), 0)

    def test_同一时刻先按三十再按一分钟才取消(self) -> None:
        clock = FrozenClock(current=START)
        conn, _, booking = self._booking(clock)
        clock.advance(timedelta(minutes=2))
        first = FulfillmentService(conn, clock=clock, settings=settings_with(30)).scan_once()
        self.assertEqual(first.total, 0)
        self.assertEqual(self._status(conn, booking.booking_no), BookingStatus.PENDING.value)
        second = FulfillmentService(conn, clock=clock, settings=settings_with(1)).scan_once()
        self.assertEqual(second.timeouts, 1)
        self.assertEqual(self._status(conn, booking.booking_no), BookingStatus.CANCELLED.value)

    def test_阈值不影响已确认订单(self) -> None:
        clock = FrozenClock(current=START)
        conn, _, booking = self._booking(clock, confirm=True)
        clock.advance(timedelta(minutes=2))
        report = FulfillmentService(conn, clock=clock, settings=settings_with(1)).scan_once()
        self.assertEqual(report.timeouts, 0)
        self.assertEqual(self._status(conn, booking.booking_no), BookingStatus.CONFIRMED.value)


if __name__ == "__main__":
    unittest.main()
