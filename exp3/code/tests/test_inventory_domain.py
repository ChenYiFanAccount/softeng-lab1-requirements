"""库存领域规则用例（S2-4 三条命名必须出现：0 间 / 恰好等于余量 / 超出余量）。"""

from __future__ import annotations

import unittest
from datetime import date

from app.domain.errors import NoAvailabilityError, ValidationError
from app.domain.inventory import (
    assert_can_occupy,
    plan_occupancy,
    range_limit_message,
    range_remaining,
)
from app.domain.models import RoomInventory


def row(stay_date: str, available: int, occupied: int = 0, status: str = "ON_SALE"):
    """构造一行库存（日期用 ``2027-03-01`` 这种字符串写，读起来对齐用例名）。"""
    return RoomInventory(
        room_type_id=1,
        stay_date=date.fromisoformat(stay_date),
        available_rooms=available,
        occupied_rooms=occupied,
        sale_status=status,
    )


class RequestZeroRoomsTest(unittest.TestCase):
    """请求 0 间是**参数错误**（422），不是"卖完了"（409）——两者提示必须区分。"""

    def test_请求0间被拒为参数错误(self) -> None:
        """0 间必须抛 ``ValidationError``，且不能当成余量不足。"""
        with self.assertRaises(ValidationError) as raised:
            assert_can_occupy([row("2027-03-01", 5)], 0)
        self.assertEqual(raised.exception.http_status, 422)
        self.assertNotIsInstance(raised.exception, NoAvailabilityError)


class ExactRemainingTest(unittest.TestCase):
    """恰好等于余量必须放行：边界少放一间就是少卖一间。"""

    def test_请求恰好等于余量时放行(self) -> None:
        """3 间余量、请求 3 间 → 通过，且计划里每行占用 +3。"""
        inventories = [row("2027-03-01", 5, 2), row("2027-03-02", 5, 1)]
        self.assertEqual(range_remaining(inventories), 3)
        plan = plan_occupancy(inventories, 3)
        self.assertEqual(
            [new_occupied for _, new_occupied in plan.new_occupied],
            [5, 4],
        )
        self.assertEqual(plan.dates, (date(2027, 3, 1), date(2027, 3, 2)))


class OverRemainingTest(unittest.TestCase):
    """超出余量必须拒绝，且拒绝信息要能直接显示"3 月 2 日只剩 1 间"。"""

    def test_请求超出余量时拒绝(self) -> None:
        """第二晚只剩 1 间，请求 2 间 → 409，且 details 指向该日期。"""
        inventories = [row("2027-03-01", 5), row("2027-03-02", 3, 2)]
        with self.assertRaises(NoAvailabilityError) as raised:
            assert_can_occupy(inventories, 2)
        self.assertEqual(raised.exception.http_status, 409)
        self.assertEqual(raised.exception.details["stay_date"], "2027-03-02")
        self.assertEqual(raised.exception.details["remaining"], 1)


class SuspendedAndMissingRowTest(unittest.TestCase):
    """停售与缺行一律按余量 0 处理：宁可拒绝，也不默认"无限可订"。"""

    def test_停售日即使有余量也拒绝(self) -> None:
        """停售日的余量不参与售卖，抛 409 且 details 带停售状态。"""
        with self.assertRaises(NoAvailabilityError) as raised:
            assert_can_occupy([row("2027-03-01", 9, 0, status="SUSPENDED")], 1)
        self.assertEqual(raised.exception.details["sale_status"], "SUSPENDED")

    def test_区间没有库存行时报构造错误(self) -> None:
        """整段区间没有库存行是调用方的构造错误（422），不是"没房"。"""
        with self.assertRaises(ValidationError):
            assert_can_occupy([], 1)

    def test_区间可订上限取各日最小值(self) -> None:
        """``range_remaining`` 取最小值；停售日把上限压到 0；空集合为 0。"""
        self.assertEqual(
            range_remaining([row("2027-03-01", 5, 4), row("2027-03-02", 2)]),
            1,
        )
        self.assertEqual(
            range_remaining([row("2027-03-01", 5), row("2027-03-02", 5, status="SUSPENDED")]),
            0,
        )
        self.assertEqual(range_remaining([]), 0)

    def test_拒绝提示文案统一(self) -> None:
        """界面与 409 响应共用同一句话，避免两处措辞不一致。"""
        self.assertEqual(range_limit_message(1, 2), "余量不足：仅剩 1 间，请求 2 间")


if __name__ == "__main__":
    unittest.main()
