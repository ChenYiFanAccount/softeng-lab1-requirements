"""S5-1：报表数字必须能对上**独立写的 SQL**。

判据要求 ``assertEqual(报表函数结果, 独立SQL结果)``，且口径不能自己证自己。
所以本文件里的期望值一律用裸 ``conn.execute`` + 手写聚合算出来，不调用
``ReportService`` 的任何方法，也不复用 ``report_repository`` 的查询——

- 报表口径（有效订单 + 当时价 + 千分比）与 SQL 写法刻意不同（Python 侧聚合 vs
  SQL 侧 GROUP BY），两条路径只有在数据真的对得上时才相等；
- 比对的是**数字**，不是实现：即使以后把报表改成预聚合表，这些用例仍然成立。

两种跑法都要成立（包模式 / discover），因此顶部先引导 ``sys.path``。
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
from app.application.report_service import ReportService, permille  # noqa: E402
from app.domain.enums import ActorRole, BookingEvent, BookingStatus  # noqa: E402

try:
    from code.tests import support
except ImportError:
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring
# 说明：本模块的用例名本身就是命题（中文），逐个补 docstring 只会重复方法名。

START = date(2027, 3, 1)
END = date(2027, 3, 6)
GUEST_LOGIN = "13900000001"


def _inventory_days(conn, fixture: dict[str, int]) -> None:  # noqa: ANN001
    day = START
    while day < END + timedelta(days=1):
        support.insert_inventory(conn, fixture["room_type_id"], day.isoformat(), 5)
        day += timedelta(days=1)


class ReportMatchesSqlTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """三条链路造出真实数据，再用独立 SQL 复算。

    夹具属性多（连接、夹具主键、两位身份、时钟、三个服务、两个订单号）是"每条用例
    都要一整套真实数据"的直接结果，拆基类只会把造数步骤藏远。
    """

    def setUp(self) -> None:
        self._stack = contextlib.ExitStack()
        conn, self._db_path = self._stack.enter_context(support.temp_database())
        self.conn = conn
        self.fixture = support.insert_fixture(conn)
        _inventory_days(conn, self.fixture)
        self.clock = FrozenClock(current=datetime(2027, 2, 1, 9, 0, 0))
        self.service = BookingAppService(conn, clock=self.clock)
        self.guest = Actor(
            account_id=self.fixture["guest_id"], role=ActorRole.CUSTOMER, login_name=GUEST_LOGIN
        )
        self.staff = Actor(
            account_id=self.fixture["staff_id"],
            role=ActorRole.HOTEL_STAFF,
            hotel_id=self.fixture["hotel_id"],
            login_name="13900000002",
        )
        self.report = ReportService(conn)
        self._seed_orders()

    def tearDown(self) -> None:
        self._stack.close()

    # ------------------------------------------------------------------ 造数

    def _add_guest(self, login_name: str) -> Actor:
        """再造一位顾客：重复预订校验是"同一顾客"口径，多个顾客才能造出交叉间夜。"""
        cursor = self.conn.execute(
            "INSERT INTO user_account (login_name, password_hash, role, hotel_id, status,"
            " created_at) VALUES (?, 'x', 'CUSTOMER', NULL, 'ACTIVE', '2026-11-25 00:00:00')",
            (login_name,),
        )
        return Actor(
            account_id=int(cursor.lastrowid), role=ActorRole.CUSTOMER, login_name=login_name
        )

    # ------------------------------------------------------------------ 造数

    def _place(self, guest: Actor, check_in: date, check_out: date, rooms: int):
        """下单并返回订单（订单号由服务生成，不再额外改写库）。"""
        command = PlaceBookingCommand(
            guest_id=guest.account_id,
            hotel_id=self.fixture["hotel_id"],
            room_type_id=self.fixture["room_type_id"],
            check_in_date=check_in,
            check_out_date=check_out,
            room_count=rooms,
        )
        return self.service.place_booking(command, guest)

    def _seed_orders(self) -> None:
        """三张单：两张有效（一待确认一已确认），一张已取消；三位顾客互不冲突。"""
        second_guest = self._add_guest("13900000011")
        third_guest = self._add_guest("13900000012")
        first = self._place(self.guest, date(2027, 3, 1), date(2027, 3, 3), 2)
        second = self._place(second_guest, date(2027, 3, 2), date(2027, 3, 4), 1)
        third = self._place(third_guest, date(2027, 3, 3), date(2027, 3, 5), 1)
        self.service.apply_event(first.booking_no, BookingEvent.CONFIRM, self.staff)
        self.service.apply_event(second.booking_no, BookingEvent.CONFIRM, self.staff)
        self.service.apply_event(third.booking_no, BookingEvent.CONFIRM, self.staff)
        self.service.cancel_booking(third.booking_no, third_guest, reason="行程变化")
        self.confirmed_no = second.booking_no
        self.cancelled_no = third.booking_no

    # ------------------------------------------------------------------ 独立 SQL

    def _sql_sold_by_day(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT n.stay_date AS stay_date, SUM(n.room_count) AS sold"
            " FROM booking_night n JOIN booking b ON b.id = n.booking_id"
            " WHERE b.status IN ('PENDING', 'CONFIRMED', 'CHECKED_IN')"
            " AND n.stay_date >= ? AND n.stay_date < ?"
            " GROUP BY n.stay_date",
            (START.isoformat(), END.isoformat()),
        ).fetchall()
        return {str(row["stay_date"]): int(row["sold"]) for row in rows}

    def _sql_capacity_by_day(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT stay_date AS stay_date, SUM(available_rooms) AS total"
            " FROM room_inventory WHERE stay_date >= ? AND stay_date < ?"
            " GROUP BY stay_date",
            (START.isoformat(), END.isoformat()),
        ).fetchall()
        return {str(row["stay_date"]): int(row["total"]) for row in rows}

    def _sql_revenue_by_day(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT n.stay_date AS stay_date,"
            " SUM(n.unit_price_cents * n.room_count) AS revenue"
            " FROM booking_night n JOIN booking b ON b.id = n.booking_id"
            " WHERE b.status IN ('PENDING', 'CONFIRMED', 'CHECKED_IN')"
            " AND n.stay_date >= ? AND n.stay_date < ?"
            " GROUP BY n.stay_date",
            (START.isoformat(), END.isoformat()),
        ).fetchall()
        return {str(row["stay_date"]): int(row["revenue"]) for row in rows}

    def _sql_status_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status AS status, COUNT(*) AS total FROM booking GROUP BY status"
        ).fetchall()
        return {str(row["status"]): int(row["total"]) for row in rows}

    # ------------------------------------------------------------------ 比对

    def test_逐日营收与独立SQL一致(self) -> None:
        actual = {
            row.stay_date: row.revenue_cents for row in self.report.revenue_by_day(START, END)
        }
        expected = self._sql_revenue_by_day()
        self.assertEqual(actual, expected)
        # 取消单的间夜必须已经消失（否则营收会把退掉的房算进去）
        self.assertNotIn("2027-03-04", actual)

    def test_逐日入住率与独立SQL一致(self) -> None:
        sold = self._sql_sold_by_day()
        capacity = self._sql_capacity_by_day()
        actual = {
            row.stay_date: (row.sold_room_nights, row.available_room_nights, row.occupancy_permille)
            for row in self.report.occupancy_by_day(START, END)
        }
        expected: dict[str, tuple[int, int, int]] = {}
        for stay_date, capacity_of_day in capacity.items():
            sold_nights = sold.get(stay_date, 0)
            expected[stay_date] = (
                sold_nights,
                capacity_of_day,
                permille(sold_nights, capacity_of_day),
            )
        self.assertEqual(actual, expected)
        self.assertEqual(actual["2027-03-01"], (2, 5, 400))
        self.assertEqual(actual["2027-03-02"], (3, 5, 600))

    def test_状态计数与独立SQL一致(self) -> None:
        self.assertEqual(self.report.status_counts(), self._sql_status_counts())

    def test_区间汇总与独立SQL一致(self) -> None:
        summary = self.report.summary(START, END)
        sold = sum(self._sql_sold_by_day().values())
        capacity = sum(self._sql_capacity_by_day().values())
        revenue = sum(self._sql_revenue_by_day().values())
        counts = self._sql_status_counts()
        self.assertEqual(summary.sold_room_nights, sold)
        self.assertEqual(summary.available_room_nights, capacity)
        self.assertEqual(summary.revenue_cents, revenue)
        self.assertEqual(summary.occupancy_permille, sold * 1000 // capacity)
        self.assertEqual(summary.order_total, sum(counts.values()))
        self.assertEqual(summary.cancelled_orders, counts.get(BookingStatus.CANCELLED.value, 0))
        self.assertEqual(
            summary.cancel_rate_permille,
            counts.get(BookingStatus.CANCELLED.value, 0) * 1000 // sum(counts.values()),
        )

    def test_按月汇总等于逐日之和(self) -> None:
        monthly = self.report.monthly_revenue(START, END)
        daily_total = sum(row.revenue_cents for row in self.report.revenue_by_day(START, END))
        self.assertEqual(monthly, {"2027-03": daily_total})

    def test_报表只读不影响订单与库存(self) -> None:
        before = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM booking) AS b,"
            " (SELECT SUM(occupied_rooms) FROM room_inventory) AS occ,"
            " (SELECT COUNT(*) FROM audit_log) AS a"
        ).fetchone()
        self.report.summary(START, END)
        self.report.occupancy_by_day(START, END)
        self.report.monthly_revenue(START, END)
        after = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM booking) AS b,"
            " (SELECT SUM(occupied_rooms) FROM room_inventory) AS occ,"
            " (SELECT COUNT(*) FROM audit_log) AS a"
        ).fetchone()
        self.assertEqual(tuple(before), tuple(after))


if __name__ == "__main__":
    unittest.main()
