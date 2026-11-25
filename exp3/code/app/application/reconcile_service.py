"""库存对账（M10 → M3 只读侧）：两条独立来源比对，只告警、不改数据。

对齐 `exp2/设计基线/03_数据设计.md` §7：

- **左侧**读 ``room_inventory.occupied_rooms``（库存事实）；
- **右侧**从有效订单的逐晚快照 ``booking_night`` 重新加总（订单事实）；
- 两者不等即告警，告警行必须带**房型 / 日期 / 左侧值 / 右侧值 / 涉及订单号**；
- **不比对可售间数**（维修、封房会让它合法地偏离总房量，比进来只会产生假告警）；
- **不自动改库存**：差异由管理员确认后走 ``InventoryAppService`` 修正并写审计，
  否则自动修正会把 bug 掩盖掉，也无法追责；
- 任务只读、幂等：重复执行不改变任何数据。

为什么要"两条独立来源"而不是复用报表的聚合：报表和对账若共用一个函数，
对账就变成"自己和自己比"，永远 diff=0（S5-1/S5-2 判据防的就是这个）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from app.infrastructure.db.report_repository import (
    SqliteReconcileRepository,
)


@dataclass(slots=True)
class ReconcileDifference:
    """一处不一致：某房型某天，库存占用与订单汇总对不上。"""

    room_type_id: int
    stay_date: str
    inventory_occupied: int
    orders_occupied: int
    booking_nos: tuple[str, ...] = ()

    @property
    def diff(self) -> int:
        """左侧 − 右侧；正数=库存多占（少卖），负数=库存漏占（超卖风险）。"""
        return self.inventory_occupied - self.orders_occupied

    def alert_line(self) -> str:
        """一条可粘贴进告警渠道的文本（含日期与订单号）。

        没有关联订单时**不能**只写 ``bookings=-``：那让运维分不清"漏了打印"还是
        "确实没有订单"。显式写原因，S5-2 的"告警必须含订单号"才经得起真实数据
        （G3-R1-01 第 3 条后果）。
        """
        if self.booking_nos:
            orders = ",".join(self.booking_nos)
        elif self.orders_occupied == 0:
            orders = "NONE(无有效订单，库存多占)"
        else:
            orders = "NONE(订单缺订单号，数据异常)"
        return (
            f"ALERT room_type={self.room_type_id} stay_date={self.stay_date} "
            f"inventory={self.inventory_occupied} orders={self.orders_occupied} "
            f"diff={self.diff} bookings={orders}"
        )


@dataclass(slots=True)
class ReconcileReport:
    """一次对账的完整结果。"""

    start_date: str
    end_date: str
    checked_pairs: int
    differences: list[ReconcileDifference] = field(default_factory=list)

    @property
    def diff_total(self) -> int:
        """所有差异的绝对值之和（0 表示账平）。"""
        return sum(abs(item.diff) for item in self.differences)

    @property
    def is_clean(self) -> bool:
        """是否无差异。"""
        return not self.differences

    def to_lines(self) -> list[str]:
        """对账输出行：首行给 ``diff=<总数>``，随后每处差异一行。"""
        lines = [
            f"checked_pairs={self.checked_pairs} diff={self.diff_total}",
        ]
        lines.extend(item.alert_line() for item in self.differences)
        if self.is_clean:
            lines.append("status=OK")
        return lines


class ReconcileService:
    """按区间比对库存占用与有效订单汇总。"""

    def __init__(
        self, conn: sqlite3.Connection, repository: SqliteReconcileRepository | None = None
    ) -> None:
        """装配：默认用同一连接建只读查询对象。"""
        self._repo = repository or SqliteReconcileRepository(conn)

    def check(self, start: date, end: date, hotel_id: int | None = None) -> ReconcileReport:
        """对 ``[start, end)`` 逐 (房型, 日期) 比对两侧。"""
        left = {
            (row.room_type_id, row.stay_date): row.occupied_rooms
            for row in self._repo.inventory_side(start, end, hotel_id)
        }
        right: dict[tuple[int, str], int] = {}
        bookings: dict[tuple[int, str], list[str]] = {}
        for row in self._repo.order_side(start, end, hotel_id):
            key = (row.room_type_id, row.stay_date)
            right[key] = right.get(key, 0) + row.room_count
            bookings.setdefault(key, []).append(row.booking_no)

        pairs = set(left) | set(right)
        differences: list[ReconcileDifference] = []
        for key in sorted(pairs):
            inventory_occupied = left.get(key, 0)
            orders_occupied = right.get(key, 0)
            if inventory_occupied == orders_occupied:
                continue
            room_type_id, stay_date = key
            differences.append(
                ReconcileDifference(
                    room_type_id=room_type_id,
                    stay_date=stay_date,
                    inventory_occupied=inventory_occupied,
                    orders_occupied=orders_occupied,
                    booking_nos=tuple(sorted(bookings.get(key, []))),
                )
            )
        return ReconcileReport(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            checked_pairs=len(pairs),
            differences=differences,
        )

    def format_report(self, report: ReconcileReport) -> str:
        """把结果拼成一段可打印文本（无差异时含 ``diff=0``）。"""
        return "\n".join(report.to_lines())
