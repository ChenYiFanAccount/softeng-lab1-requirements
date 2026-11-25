"""统计报表（M8）：入住率、订单量、营收，按日/月汇总，全平台与单店两视角。

口径三条，全部写死在代码里，不靠调用方自觉：

1. **只算有效订单**（待确认/已确认/已入住）。已取消、已退房、未入住的订单不计入
   营收与间夜——退房的单营收已经发生过，为什么不算？因为本系统按**入住日**归属
   营收（客房收入在住的那一晚确认），退房单的间夜仍在入住日上，状态变成已退房后
   统计会跳变；课程口径取"有效订单"，报告里明确写这一点。
2. **入住率 = 卖出间夜 / 挂牌可售间夜**，用**千分比整数**表达（``permille``），
   不用浮点：一是不让 ``float`` 混进金额与比率口径（S2-5），二是整数可比对。
3. **营收用"当时价"**，即逐晚快照 ``booking_night.unit_price_cents``，不是当前房价；
   改价只影响新订单（REQ-006）。

报表只读：本模块不写任何表，也不改库存；差异处置见 ``reconcile_service``。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from app.infrastructure.db.report_repository import SqliteReportRepository

#: 订单"已取消"状态码，用于取消率
CANCELLED_CODE = "CANCELLED"

#: 比率精度：千分比（0.1% 一档），报告与界面都按这个粒度展示
PERMILLE = 1000


def permille(part: int, whole: int) -> int:
    """把 ``part/whole`` 换成千分比整数；分母为 0 时返回 0。"""
    return 0 if whole <= 0 else part * PERMILLE // whole


@dataclass(slots=True)
class OccupancyRow:
    """某一天的入住情况。"""

    stay_date: str
    sold_room_nights: int
    available_room_nights: int
    occupancy_permille: int


@dataclass(slots=True)
class RevenueRow:
    """某一天的营收与间夜。"""

    stay_date: str
    room_nights: int
    revenue_cents: int


@dataclass(slots=True)
class ReportSummary:  # pylint: disable=too-many-instance-attributes
    """区间汇总（报表首页那几张大数字）。

    字段数与报表指标一一对应（间夜、容量、入住率、营收、订单量、取消数、取消率），
    拆成小对象反而让界面要组合三次；这里按"一张报表卡片一组数字"保留。
    """

    start_date: str
    end_date: str
    sold_room_nights: int
    available_room_nights: int
    occupancy_permille: int
    revenue_cents: int
    order_total: int
    cancelled_orders: int
    cancel_rate_permille: int


class ReportService:
    """按日/月汇总指标（只读）。"""

    def __init__(
        self, conn: sqlite3.Connection, repository: SqliteReportRepository | None = None
    ) -> None:
        """装配：默认用同一连接建只读仓储。"""
        self._repo = repository or SqliteReportRepository(conn)

    def occupancy_by_day(
        self, start: date, end: date, hotel_id: int | None = None
    ) -> list[OccupancyRow]:
        """逐日入住率（只列有挂牌库存的日期）。"""
        sold = self._repo.sold_room_nights(start, end, hotel_id)
        available = self._repo.available_room_nights(start, end, hotel_id)
        rows: list[OccupancyRow] = []
        for stay_date in sorted(available):
            sold_nights = sold.get(stay_date, 0)
            capacity = available[stay_date]
            rows.append(
                OccupancyRow(
                    stay_date=stay_date,
                    sold_room_nights=sold_nights,
                    available_room_nights=capacity,
                    occupancy_permille=permille(sold_nights, capacity),
                )
            )
        return rows

    def revenue_by_day(
        self, start: date, end: date, hotel_id: int | None = None
    ) -> list[RevenueRow]:
        """逐日营收（分）与间夜数。"""
        revenue = self._repo.revenue_by_day(start, end, hotel_id)
        nights = self._repo.sold_room_nights(start, end, hotel_id)
        return [
            RevenueRow(
                stay_date=stay_date,
                room_nights=nights.get(stay_date, 0),
                revenue_cents=amount,
            )
            for stay_date, amount in sorted(revenue.items())
        ]

    def status_counts(self, hotel_id: int | None = None) -> dict[str, int]:
        """各状态订单数（界面上那排状态标签）。"""
        return self._repo.status_counts(hotel_id)

    def summary(self, start: date, end: date, hotel_id: int | None = None) -> ReportSummary:
        """区间汇总：间夜、入住率、营收、订单量与取消率。"""
        sold = sum(self._repo.sold_room_nights(start, end, hotel_id).values())
        capacity = sum(self._repo.available_room_nights(start, end, hotel_id).values())
        revenue = sum(self._repo.revenue_by_day(start, end, hotel_id).values())
        counts = self._repo.status_counts(hotel_id)
        order_total = sum(counts.values())
        cancelled = counts.get(CANCELLED_CODE, 0)
        return ReportSummary(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            sold_room_nights=sold,
            available_room_nights=capacity,
            occupancy_permille=permille(sold, capacity),
            revenue_cents=revenue,
            order_total=order_total,
            cancelled_orders=cancelled,
            cancel_rate_permille=permille(cancelled, order_total),
        )

    def monthly_revenue(
        self, start: date, end: date, hotel_id: int | None = None
    ) -> dict[str, int]:
        """按月汇总营收（``YYYY-MM`` → 分），趋势图用。"""
        buckets: dict[str, int] = {}
        for row in self.revenue_by_day(start, end, hotel_id):
            month = row.stay_date[:7]
            buckets[month] = buckets.get(month, 0) + row.revenue_cents
        return dict(sorted(buckets.items()))
