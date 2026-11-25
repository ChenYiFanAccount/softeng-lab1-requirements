"""S5-2：对账必须能发现**人为造出来**的差异，且告警里要看得到订单号与日期。

判据的两半都要证：

1. 平账时输出 ``diff=0``——否则"发现差异"无从判断是不是永远告警；
2. 人为把库存占用改一位，告警行必须带**房型 / 日期 / 两侧值 / 涉及订单号**，
   否则运维拿到告警也不知道去找哪张单。

对账两侧是两条独立查询（库存表 vs 订单逐晚快照），本文件用 ``UPDATE
room_inventory`` 制造差异——如果右侧也读库存表，这些用例就会失败，正好起到
"口径独立"的守门作用。
"""

from __future__ import annotations

import contextlib
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
from app.application.reconcile_service import ReconcileService  # noqa: E402
from app.domain.enums import ActorRole, BookingEvent  # noqa: E402

try:
    from code.tests import support
except ImportError:
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring
# 说明：本模块的用例名本身就是命题（中文），逐个补 docstring 只会重复方法名。

START = date(2027, 3, 1)
END = date(2027, 3, 5)


class ReconcileAlertTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """一张已确认订单 + 三天库存，作为"账平"的基线。

    ``setUp`` 里挂 11 个属性是测试夹具的常态（连接、夹具主键、两个身份、两个服务、
    一张订单号）；抽成公共基类只会把"本用例要什么"藏到另一个文件。
    """

    def setUp(self) -> None:
        self._stack = contextlib.ExitStack()
        conn, _ = self._stack.enter_context(support.temp_database())
        self.conn = conn
        self.fixture = support.insert_fixture(conn)
        day = START
        while day < END + timedelta(days=1):
            support.insert_inventory(conn, self.fixture["room_type_id"], day.isoformat(), 5)
            day += timedelta(days=1)
        self.clock = FrozenClock(current=datetime(2027, 2, 1, 9, 0, 0))
        self.bookings = BookingAppService(conn, clock=self.clock)
        self.guest = Actor(
            account_id=self.fixture["guest_id"], role=ActorRole.CUSTOMER, login_name="13900000001"
        )
        self.staff = Actor(
            account_id=self.fixture["staff_id"],
            role=ActorRole.HOTEL_STAFF,
            hotel_id=self.fixture["hotel_id"],
            login_name="13900000002",
        )
        self.booking = self.bookings.place_booking(
            PlaceBookingCommand(
                guest_id=self.fixture["guest_id"],
                hotel_id=self.fixture["hotel_id"],
                room_type_id=self.fixture["room_type_id"],
                check_in_date=date(2027, 3, 1),
                check_out_date=date(2027, 3, 3),
                room_count=2,
            ),
            self.guest,
        )
        self.bookings.apply_event(self.booking.booking_no, BookingEvent.CONFIRM, self.staff)
        self.reconcile = ReconcileService(conn)

    def tearDown(self) -> None:
        self._stack.close()

    def _occupied(self, stay_date: str) -> int:
        row = self.conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ? AND stay_date = ?",
            (self.fixture["room_type_id"], stay_date),
        ).fetchone()
        return int(row["occupied_rooms"])

    def test_账平时输出diff等于0(self) -> None:
        report = self.reconcile.check(START, END)
        self.assertTrue(report.is_clean)
        self.assertEqual(report.diff_total, 0)
        self.assertEqual(report.checked_pairs, 4)
        text = self.reconcile.format_report(report)
        self.assertIn("diff=0", text)
        self.assertIn("status=OK", text)
        self.assertNotIn("ALERT", text)

    def test_人为把库存占用加一会告警并带订单号与日期(self) -> None:
        self.conn.execute(
            "UPDATE room_inventory SET occupied_rooms = occupied_rooms + 1"
            " WHERE room_type_id = ? AND stay_date = '2027-03-02'",
            (self.fixture["room_type_id"],),
        )
        report = self.reconcile.check(START, END)
        self.assertEqual(len(report.differences), 1)
        difference = report.differences[0]
        self.assertEqual(difference.stay_date, "2027-03-02")
        self.assertEqual((difference.inventory_occupied, difference.orders_occupied), (3, 2))
        self.assertEqual(difference.diff, 1)
        self.assertIn(self.booking.booking_no, difference.booking_nos)
        text = self.reconcile.format_report(report)
        self.assertIn("diff=1", text)
        self.assertIn("2027-03-02", text)
        self.assertIn(self.booking.booking_no, text)
        self.assertIn("ALERT", text)

    def test_库存漏占也能发现且差额为负(self) -> None:
        self.conn.execute(
            "UPDATE room_inventory SET occupied_rooms = occupied_rooms - 1"
            " WHERE room_type_id = ? AND stay_date = '2027-03-01'",
            (self.fixture["room_type_id"],),
        )
        report = self.reconcile.check(START, END)
        self.assertEqual(len(report.differences), 1)
        self.assertEqual(report.differences[0].diff, -1)
        self.assertEqual(report.diff_total, 1)
        self.assertIn("diff=-1", report.differences[0].alert_line())

    def test_已取消订单不计入右侧所以账仍然平(self) -> None:
        self.bookings.cancel_booking(self.booking.booking_no, self.guest, reason="测试取消")
        self.assertEqual(self._occupied("2027-03-01"), 0)
        report = self.reconcile.check(START, END)
        self.assertTrue(report.is_clean, "取消后两侧都应归零；若右侧仍算旧单就会报警")

    def test_退房后对账diff等于零(self) -> None:
        """退房不释放占用，右侧若排除 CHECKED_OUT 就会每单误报 diff=2（G3-R1-01）。"""
        for event in (BookingEvent.CHECK_IN, BookingEvent.CHECK_OUT):
            self.bookings.apply_event(self.booking.booking_no, event, self.staff)
        self.assertEqual(self._occupied("2027-03-01"), 2, "退房不应释放库存占用")

        report = self.reconcile.check(START, END)
        self.assertTrue(report.is_clean, f"正常退房不应产生差异，实得 {report.to_lines()}")
        self.assertEqual(report.diff_total, 0)
        text = self.reconcile.format_report(report)
        self.assertIn("diff=0", text)
        self.assertIn("status=OK", text)
        self.assertNotIn("ALERT", text)

    def test_告警行不得出现裸bookings减号(self) -> None:
        """无关联订单时必须写出可读原因，不能只给 ``bookings=-``（G3-R1-01 第 3 条后果）。"""
        # 3-04 有库存行但没有任何订单：占用被改成 1 就是"库存多占、无有效订单"
        self.conn.execute(
            "UPDATE room_inventory SET occupied_rooms = 1"
            " WHERE room_type_id = ? AND stay_date = '2027-03-04'",
            (self.fixture["room_type_id"],),
        )
        report = self.reconcile.check(START, END)
        self.assertEqual(len(report.differences), 1)
        line = report.differences[0].alert_line()
        self.assertNotIn("bookings=-", line)
        self.assertIn("bookings=NONE(无有效订单，库存多占)", line)
        self.assertIn("2027-03-04", line)

    def test_对账只读不修改库存与审计(self) -> None:
        before_occ = self._occupied("2027-03-01")
        before_audit = self.conn.execute(
            "SELECT COUNT(*) AS total FROM audit_log"
        ).fetchone()["total"]
        self.conn.execute(
            "UPDATE room_inventory SET occupied_rooms = occupied_rooms + 1"
            " WHERE room_type_id = ? AND stay_date = '2027-03-02'",
            (self.fixture["room_type_id"],),
        )
        for _ in range(3):
            self.reconcile.check(START, END)
        self.assertEqual(self._occupied("2027-03-01"), before_occ)
        after_audit = self.conn.execute(
            "SELECT COUNT(*) AS total FROM audit_log"
        ).fetchone()["total"]
        self.assertEqual(after_audit, before_audit)


if __name__ == "__main__":
    unittest.main()
