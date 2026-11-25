"""库存规则：余量判定与占用计划（纯函数，不碰数据库）。

三条判定按"必须写成用例"的顺序排列（S2-4）：

* 请求 **0 间** → 参数错误（422），不是"余量不足"；
* 请求 **恰好等于余量** → 允许（边界必须放行，否则少卖一间）；
* 请求 **超出余量** → 拒绝（409），且不得产生任何占用副作用。

停售日（``SUSPENDED``）与"整段区间缺行"一律按余量 0 处理：宁可拒绝，
也不能因为缺数据而默认无限可订。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from app.domain.errors import NoAvailabilityError, ValidationError
from app.domain.models import RoomInventory


@dataclass(frozen=True, slots=True)
class OccupancyPlan:
    """一次占用计划：把"改哪几行、各加几间"先算清楚，再交给事务执行。"""

    room_count: int
    dates: tuple[date, ...]
    inventory: tuple[RoomInventory, ...]

    @property
    def new_occupied(self) -> tuple[tuple[RoomInventory, int], ...]:
        """每行库存占用后的新值（整数相加，不做浮点/百分比换算）。"""
        return tuple(
            (row, row.occupied_rooms + self.room_count) for row in self.inventory
        )


def range_remaining(inventories: Iterable[RoomInventory]) -> int:
    """区间可订上限 = 各日余量的最小值；停售日视为 0。

    Args:
        inventories: 覆盖该区间的库存行（可少行）。

    Returns:
        可订间数上限；空集合返回 0。
    """
    limits = [
        row.remaining if row.is_on_sale else 0
        for row in inventories
    ]
    return min(limits) if limits else 0


def assert_can_occupy(inventories: Sequence[RoomInventory], room_count: int) -> None:
    """校验一次占用请求。

    Args:
        inventories: 该区间每一晚的库存行（调用方保证已按日期对齐、长度=天数）。
        room_count: 请求间数。

    Raises:
        ValidationError: 间数 ≤ 0，或区间没有库存行（构造错误）。
        NoAvailabilityError: 任一日停售、缺行或余量不足；``details`` 里带上首个
            不满足的日期与余量，方便界面直接提示"3 月 2 日只剩 0 间"。
    """
    if room_count <= 0:
        raise ValidationError("间数必须大于 0", room_count=room_count)
    if not inventories:
        raise ValidationError("区间内没有库存行，无法判定余量")
    for row in inventories:
        if not row.is_on_sale:
            raise NoAvailabilityError(
                "当日已停售",
                stay_date=str(row.stay_date),
                sale_status=row.sale_status,
            )
        if room_count > row.remaining:
            raise NoAvailabilityError(
                "余量不足",
                stay_date=str(row.stay_date),
                requested=room_count,
                remaining=row.remaining,
            )


def plan_occupancy(
    inventories: Sequence[RoomInventory], room_count: int
) -> OccupancyPlan:
    """校验并生成占用计划（只计算，不写库）。

    Args:
        inventories: 该区间每一晚的库存行。
        room_count: 请求间数。

    Returns:
        :class:`OccupancyPlan`；``new_occupied`` 可直接交给仓储逐行 ``UPDATE``。

    Raises:
        ValidationError: 间数 ≤ 0 或区间为空。
        NoAvailabilityError: 任一日不可订。
    """
    assert_can_occupy(inventories, room_count)
    return OccupancyPlan(
        room_count=room_count,
        dates=tuple(row.stay_date for row in inventories),
        inventory=tuple(inventories),
    )


def range_limit_message(remaining: int, room_count: int) -> str:
    """生成统一的拒绝提示（界面与 409 响应共用一句话）。"""
    return f"余量不足：仅剩 {remaining} 间，请求 {room_count} 间"
