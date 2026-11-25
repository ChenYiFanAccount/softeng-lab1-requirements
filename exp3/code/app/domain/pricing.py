"""计价规则（全部整数分运算）。

三条纪律：

1. **禁止浮点**：金额只用 ``int``（分）。浮点函数与四舍五入在本模块一律不许出现
   （S2-5 判据用 grep 检查字面量），因为浮点累加误差会让对账差 1 分。
2. **逐晚计价**：总价 = Σ(每晚单价 × 间数)，与 ``booking_night`` 快照一一对应。
3. **均价只用于展示**：向下取整，且明确标注"仅供参考"，不能反过来当总价用。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.errors import ValidationError
from app.domain.models import BookingNight, RoomPrice


@dataclass(frozen=True, slots=True)
class Quote:
    """一次报价的完整结果（可整段写进订单与报告）。"""

    check_in_date: date
    check_out_date: date
    room_count: int
    total_cents: int
    nightly: tuple[RoomPrice, ...]

    @property
    def nights(self) -> int:
        """占用天数（退房日 − 入住日）。"""
        return (self.check_out_date - self.check_in_date).days

    @property
    def average_nightly_cents(self) -> int:
        """均价（分）＝ 总价 // 天数，向下取整；只用于列表页展示。"""
        return self.total_cents // self.nights if self.nights else 0

    def to_booking_nights(self, booking_id: int) -> list[BookingNight]:
        """把报价固化成逐晚快照（订单创建时调用）。"""
        return [
            BookingNight(
                booking_id=booking_id,
                stay_date=price.stay_date,
                unit_price_cents=price.unit_price_cents,
                room_count=self.room_count,
            )
            for price in self.nightly
        ]


def stay_dates(check_in_date: date, check_out_date: date) -> list[date]:
    """返回入住期间每晚的日期（右开区间：退房日当天不住）。

    Args:
        check_in_date: 入住日。
        check_out_date: 退房日，必须晚于入住日。

    Returns:
        长度等于天数的日期列表。

    Raises:
        ValidationError: 退房日不晚于入住日。
    """
    if check_out_date <= check_in_date:
        raise ValidationError(
            "退房日必须晚于入住日",
            check_in=str(check_in_date),
            check_out=str(check_out_date),
        )
    nights = (check_out_date - check_in_date).days
    return [check_in_date + timedelta(days=offset) for offset in range(nights)]


def quote(
    nightly_prices: Mapping[date, int],
    check_in_date: date,
    check_out_date: date,
    room_count: int,
) -> Quote:
    """按逐日单价生成报价。

    Args:
        nightly_prices: ``{日期: 单价(分)}``，必须覆盖入住期间每一晚。
        check_in_date: 入住日。
        check_out_date: 退房日。
        room_count: 间数，必须 > 0。

    Returns:
        :class:`Quote`，其 ``total_cents`` 与逐晚小计之和严格相等。

    Raises:
        ValidationError: 间数 ≤ 0，或某晚缺价（缺价必须显式报错，不能默认 0 元）。
    """
    if room_count <= 0:
        raise ValidationError("间数必须大于 0", room_count=room_count)
    prices: list[RoomPrice] = []
    for stay_date in stay_dates(check_in_date, check_out_date):
        if stay_date not in nightly_prices:
            raise ValidationError("缺少当日价格，不能按 0 元出售", stay_date=str(stay_date))
        unit_price_cents = nightly_prices[stay_date]
        if unit_price_cents <= 0:
            raise ValidationError("单价必须大于 0", stay_date=str(stay_date))
        prices.append(
            RoomPrice(
                room_type_id=0,
                stay_date=stay_date,
                unit_price_cents=unit_price_cents,
            )
        )
    total_cents = sum(price.unit_price_cents * room_count for price in prices)
    return Quote(
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        room_count=room_count,
        total_cents=total_cents,
        nightly=tuple(prices),
    )


def total_from_nights(nights: Sequence[BookingNight]) -> int:
    """按逐晚快照汇总总价（分）——对账时与订单 ``total_price_cents`` 比对。"""
    return sum(night.subtotal_cents() for night in nights)
