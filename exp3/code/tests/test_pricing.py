"""计价用例：整数分、逐晚求和、缺价必须报错（不能按 0 元卖）。"""

from __future__ import annotations

import unittest
from datetime import date

import sys
from pathlib import Path
# 两种跑法都要成立（G2-R1-02）：`python -m unittest code.tests.X` 与
# `python -m unittest discover -s code/tests -t code`。前者不会把 code/ 放进
# sys.path，故在这里显式补一次；用 __file__ 定位，不依赖进程 cwd。
_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))
from app.domain.errors import ValidationError
from app.domain.models import BookingNight
from app.domain.pricing import Quote, quote, stay_dates, total_from_nights


class StayDatesTest(unittest.TestCase):
    """右开区间：退房日当天不住。"""

    def test_三晚的区间含三个日期(self) -> None:
        """3/1 入住、3/4 退房 → 3/1、3/2、3/3 三晚。"""
        self.assertEqual(
            stay_dates(date(2027, 3, 1), date(2027, 3, 4)),
            [date(2027, 3, 1), date(2027, 3, 2), date(2027, 3, 3)],
        )

    def test_退房日不晚于入住日被拒(self) -> None:
        """同日退房（0 晚）与倒序日期都是 422。"""
        for check_out in (date(2027, 3, 1), date(2027, 2, 28)):
            with self.subTest(check_out=check_out.isoformat()):
                with self.assertRaises(ValidationError):
                    stay_dates(date(2027, 3, 1), check_out)


class QuoteTest(unittest.TestCase):
    """报价：总价 = Σ(每晚单价 × 间数)，全部整数分。"""

    def setUp(self) -> None:
        self.prices = {
            date(2027, 3, 1): 30000,
            date(2027, 3, 2): 32000,
        }

    def test_总价等于逐晚小计之和(self) -> None:
        """两晚单价 300/320 元、2 间 → 总价 (300+320)×2 = 1240 元 = 124000 分。"""
        result = quote(self.prices, date(2027, 3, 1), date(2027, 3, 3), 2)
        self.assertEqual(result.nights, 2)
        self.assertEqual(result.total_cents, 124000)
        self.assertEqual(
            result.total_cents,
            sum(price.subtotal_cents(2) for price in result.nightly),
        )

    def test_均价向下取整只用于展示(self) -> None:
        """均价 = 总价 // 天数，整除不产生小数。"""
        result = quote(self.prices, date(2027, 3, 1), date(2027, 3, 3), 1)
        self.assertEqual(result.total_cents, 62000)
        self.assertEqual(result.average_nightly_cents, 31000)

    def test_缺少某晚价格必须报错(self) -> None:
        """缺价不能默认 0 元：漏价直接 422，避免出现"免费住一晚"。"""
        partial = {date(2027, 3, 1): 30000}
        with self.assertRaises(ValidationError) as raised:
            quote(partial, date(2027, 3, 1), date(2027, 3, 3), 1)
        self.assertEqual(raised.exception.details["stay_date"], "2027-03-02")

    def test_单价非正与间数非正都被拒(self) -> None:
        """0 元/负价与 0 间/负数间都是参数错误。"""
        with self.assertRaises(ValidationError):
            quote({date(2027, 3, 1): 0}, date(2027, 3, 1), date(2027, 3, 2), 1)
        with self.assertRaises(ValidationError):
            quote(self.prices, date(2027, 3, 1), date(2027, 3, 3), 0)

    def test_报价可固化为逐晚快照(self) -> None:
        """``to_booking_nights`` 生成的快照与报价逐晚对齐，总价可反算回来。"""
        result = quote(self.prices, date(2027, 3, 1), date(2027, 3, 3), 3)
        nights = result.to_booking_nights(booking_id=42)
        self.assertIsInstance(result, Quote)
        self.assertEqual([night.stay_date for night in nights], list(self.prices))
        self.assertEqual(total_from_nights(nights), result.total_cents)
        self.assertTrue(all(night.booking_id == 42 for night in nights))


class TotalFromNightsTest(unittest.TestCase):
    """对账用的反算：快照之和必须与订单总价一致。"""

    def test_三晚不同价的快照求和(self) -> None:
        """(10000×1) + (20000×2) + (30000×3) = 140000 分。"""
        nights = [
            BookingNight(
                booking_id=1,
                stay_date=date(2027, 3, 1),
                unit_price_cents=10000,
                room_count=1,
            ),
            BookingNight(
                booking_id=1,
                stay_date=date(2027, 3, 2),
                unit_price_cents=20000,
                room_count=2,
            ),
            BookingNight(
                booking_id=1,
                stay_date=date(2027, 3, 3),
                unit_price_cents=30000,
                room_count=3,
            ),
        ]
        self.assertEqual(total_from_nights(nights), 140000)
        self.assertEqual(total_from_nights([]), 0)


if __name__ == "__main__":
    unittest.main()
