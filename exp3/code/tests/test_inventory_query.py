"""余量查询口径（S1-5）：用例内硬编码逐日期望值，防止"改代码迁就实现"。

夹具固定为 3 晚、总房量 5：

====================  ==========  ==========  ======
日期                   可售        占用        余量
====================  ==========  ==========  ======
2027-03-01            5           2           3
2027-03-02            4           4           0
2027-03-03            5           0           5
====================  ==========  ==========  ======
"""

from __future__ import annotations

import contextlib
import unittest
from datetime import date

try:  # 跑法一：python -m unittest code.tests.test_x
    from code.tests import support
except ImportError:  # pragma: no cover - 跑法二：discover -s code/tests -t code
    import support  # type: ignore[no-redef]

from app.infrastructure.db import inventory_query

DAY1 = date(2027, 3, 1)
DAY2 = date(2027, 3, 2)
DAY3 = date(2027, 3, 3)
DAY4 = date(2027, 3, 4)


class InventoryQueryTest(unittest.TestCase):
    """逐日余量、区间上限与三值展示。"""

    def setUp(self) -> None:
        self._stack = contextlib.ExitStack()
        self.conn, _ = self._stack.enter_context(support.temp_database())
        self.fixture = support.insert_fixture(self.conn)
        room_type_id = self.fixture["room_type_id"]
        support.insert_inventory(self.conn, room_type_id, DAY1.isoformat(), 5, 2)
        support.insert_inventory(self.conn, room_type_id, DAY2.isoformat(), 4, 4)
        support.insert_inventory(self.conn, room_type_id, DAY3.isoformat(), 5, 0)

    def tearDown(self) -> None:
        self._stack.close()

    def test_daily_remaining_matches_hardcoded_expectation(self) -> None:
        """三天余量必须逐日等于硬编码字典（3 / 0 / 5）。"""
        remaining = inventory_query.daily_remaining(
            self.conn, self.fixture["room_type_id"], DAY1, DAY4
        )
        self.assertEqual(
            remaining,
            {"2027-03-01": 3, "2027-03-02": 0, "2027-03-03": 5},
        )

    def test_remaining_is_derived_not_stored(self) -> None:
        """余量派生自「可售 − 占用」，改占用立刻反映，没有独立字段可漂移。"""
        room_type_id = self.fixture["room_type_id"]
        self.conn.execute(
            "UPDATE room_inventory SET occupied_rooms = 5 WHERE room_type_id = ? AND stay_date = ?",
            (room_type_id, DAY1.isoformat()),
        )
        remaining = inventory_query.daily_remaining(self.conn, room_type_id, DAY1, DAY2)
        self.assertEqual(remaining, {"2027-03-01": 0})

    def test_range_limit_is_minimum_over_nights(self) -> None:
        """区间上限取各日最小值：含 0 余量的那一晚 → 0；只订首晚 → 3。"""
        room_type_id = self.fixture["room_type_id"]
        self.assertEqual(inventory_query.range_limit(self.conn, room_type_id, DAY1, DAY4), 0)
        self.assertEqual(inventory_query.range_limit(self.conn, room_type_id, DAY1, DAY2), 3)
        self.assertEqual(inventory_query.range_limit(self.conn, room_type_id, DAY3, DAY4), 5)

    def test_range_limit_zero_when_suspended(self) -> None:
        """停售是开关：可售间数 > 0 也订不了，区间上限必须是 0。"""
        room_type_id = self.fixture["room_type_id"]
        self.conn.execute(
            "UPDATE room_inventory SET sale_status = 'SUSPENDED'"
            " WHERE room_type_id = ? AND stay_date = ?",
            (room_type_id, DAY3.isoformat()),
        )
        self.assertEqual(inventory_query.range_limit(self.conn, room_type_id, DAY3, DAY4), 0)

    def test_missing_row_is_not_silently_available(self) -> None:
        """没有库存行的日期不进余量字典，且区间上限按 0 处理（不允许默认无限可订）。"""
        room_type_id = self.fixture["room_type_id"]
        remaining = inventory_query.daily_remaining(self.conn, room_type_id, DAY4, date(2027, 3, 6))
        self.assertEqual(remaining, {})
        self.assertEqual(
            inventory_query.range_limit(self.conn, room_type_id, DAY4, date(2027, 3, 6)),
            0,
        )

    def test_daily_rows_exposes_three_values(self) -> None:
        """界面要并列显示可售 / 占用 / 余量三个数，不能只给一个剩余量。"""
        rows = inventory_query.daily_rows(self.conn, self.fixture["room_type_id"], DAY2, DAY3)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            (row["available_rooms"], row["occupied_rooms"], row["remaining"]),
            (4, 4, 0),
        )
        self.assertEqual(row["sale_status"], "ON_SALE")

    def test_empty_range_returns_zero(self) -> None:
        """退房日不晚于入住日时区间为空，上限为 0 而不是报错。"""
        room_type_id = self.fixture["room_type_id"]
        self.assertEqual(inventory_query.range_limit(self.conn, room_type_id, DAY2, DAY2), 0)


if __name__ == "__main__":
    unittest.main()
