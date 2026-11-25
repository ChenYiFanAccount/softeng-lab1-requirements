"""报表与对账用的只读查询（M8 / M10，数据访问层）。

**为什么单独一个文件**：报表和对账都只读、且要"两边独立算一遍"。把它们
的 SQL 与业务判断分开，才能让对账拿到的左侧（库存占用）和右侧（有效订单
汇总）真的是两条互不依赖的查询——如果两边共用一个聚合函数，对账就退化成
"自己和自己比"，永远 diff=0（S5-1/S5-2 的判据正是防这个）。

本模块只做 SELECT，不含任何写入方法；对账发现差异后**不自动改库存**，
修正由管理员在界面上确认后走 `InventoryAppService` 并写审计（03_数据设计 §7）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from app.domain.enums import BookingStatus
from app.infrastructure.db.mapping import date_text

#: 计入营收与间夜的状态：有效订单 + **已退房**。
#:
#: 退房不释放占用（``CHECK_OUT`` 不在 ``RELEASING_EVENTS`` 里），那几晚确实卖出去了；
#: 若把 ``CHECKED_OUT`` 排除，客人一退房这两天的营收就会从报表里蒸发，口径变成
#: "越接近成交越不算营收"（G3-R1-01 的缺陷本体）。
REVENUE_STATUSES: tuple[BookingStatus, ...] = (
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.CHECKED_IN,
    BookingStatus.CHECKED_OUT,
)
REVENUE_VALUES: tuple[str, ...] = tuple(status.value for status in REVENUE_STATUSES)
REVENUE_PLACEHOLDERS: str = ", ".join("?" for _ in REVENUE_VALUES)

#: 对账右侧集合：必须与营收同集合——库存侧退房不释放，右侧若把已退房排除，
#: 每张正常退房的单都会留下"库存多占"的假告警（G3-R1-01）。
OCCUPYING_VALUES: tuple[str, ...] = REVENUE_VALUES
OCCUPYING_PLACEHOLDERS: str = REVENUE_PLACEHOLDERS


@dataclass(slots=True)
class InventoryRow:
    """库存左侧事实：某房型某天"已占用间数"。"""

    room_type_id: int
    stay_date: str
    occupied_rooms: int


@dataclass(slots=True)
class OrderNightRow:
    """订单右侧事实：某张有效订单在某个晚上占了几间。"""

    booking_no: str
    room_type_id: int
    stay_date: str
    room_count: int


class SqliteReportRepository:
    """报表聚合（按日/按状态/按酒店）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """保存连接（连接由调用方按工厂建好，每线程独立）。"""
        self._conn = conn

    def sold_room_nights(
        self, start: date, end: date, hotel_id: int | None = None
    ) -> dict[str, int]:
        """卖出间夜数（含已退房，左闭右开）。"""
        sql = (
            "SELECT n.stay_date AS stay_date, SUM(n.room_count) AS sold "
            "FROM booking_night n JOIN booking b ON b.id = n.booking_id "
            f"WHERE b.status IN ({REVENUE_PLACEHOLDERS}) "
            "AND n.stay_date >= ? AND n.stay_date < ? "
        )
        params: list[object] = [*REVENUE_VALUES, date_text(start), date_text(end)]
        if hotel_id is not None:
            sql += "AND b.hotel_id = ? "
            params.append(hotel_id)
        sql += "GROUP BY n.stay_date ORDER BY n.stay_date"
        rows = self._conn.execute(sql, params).fetchall()
        return {str(row["stay_date"]): int(row["sold"]) for row in rows}

    def available_room_nights(
        self, start: date, end: date, hotel_id: int | None = None
    ) -> dict[str, int]:
        """每天全平台（或某酒店）挂牌可售间数之和。"""
        sql = (
            "SELECT i.stay_date AS stay_date, SUM(i.available_rooms) AS available "
            "FROM room_inventory i JOIN room_type rt ON rt.id = i.room_type_id "
            "WHERE i.stay_date >= ? AND i.stay_date < ? "
        )
        params: list[object] = [date_text(start), date_text(end)]
        if hotel_id is not None:
            sql += "AND rt.hotel_id = ? "
            params.append(hotel_id)
        sql += "GROUP BY i.stay_date ORDER BY i.stay_date"
        rows = self._conn.execute(sql, params).fetchall()
        return {str(row["stay_date"]): int(row["available"]) for row in rows}

    def revenue_by_day(self, start: date, end: date, hotel_id: int | None = None) -> dict[str, int]:
        """每天按"当时价"算出的营收（分，含已退房）。"""
        sql = (
            "SELECT n.stay_date AS stay_date, "
            "SUM(n.unit_price_cents * n.room_count) AS revenue "
            "FROM booking_night n JOIN booking b ON b.id = n.booking_id "
            f"WHERE b.status IN ({REVENUE_PLACEHOLDERS}) "
            "AND n.stay_date >= ? AND n.stay_date < ? "
        )
        params: list[object] = [*REVENUE_VALUES, date_text(start), date_text(end)]
        if hotel_id is not None:
            sql += "AND b.hotel_id = ? "
            params.append(hotel_id)
        sql += "GROUP BY n.stay_date ORDER BY n.stay_date"
        rows = self._conn.execute(sql, params).fetchall()
        return {str(row["stay_date"]): int(row["revenue"]) for row in rows}

    def status_counts(self, hotel_id: int | None = None) -> dict[str, int]:
        """各状态订单数。"""
        sql = "SELECT status AS status, COUNT(*) AS total FROM booking "
        params: list[object] = []
        if hotel_id is not None:
            sql += "WHERE hotel_id = ? "
            params.append(hotel_id)
        sql += "GROUP BY status ORDER BY status"
        rows = self._conn.execute(sql, params).fetchall()
        return {str(row["status"]): int(row["total"]) for row in rows}


class SqliteReconcileRepository:
    """对账两侧的独立查询（左侧库存、右侧订单）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """保存连接。"""
        self._conn = conn

    def inventory_side(
        self, start: date, end: date, hotel_id: int | None = None
    ) -> list[InventoryRow]:
        """左侧：直接读 ``room_inventory.occupied_rooms``，不经过任何订单聚合。"""
        sql = (
            "SELECT i.room_type_id AS room_type_id, i.stay_date AS stay_date, "
            "SUM(i.occupied_rooms) AS occupied "
            "FROM room_inventory i JOIN room_type rt ON rt.id = i.room_type_id "
            "WHERE i.stay_date >= ? AND i.stay_date < ? "
        )
        params: list[object] = [date_text(start), date_text(end)]
        if hotel_id is not None:
            sql += "AND rt.hotel_id = ? "
            params.append(hotel_id)
        sql += "GROUP BY i.room_type_id, i.stay_date ORDER BY i.room_type_id, i.stay_date"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            InventoryRow(
                room_type_id=int(row["room_type_id"]),
                stay_date=str(row["stay_date"]),
                occupied_rooms=int(row["occupied"]),
            )
            for row in rows
        ]

    def order_side(
        self, start: date, end: date, hotel_id: int | None = None
    ) -> list[OrderNightRow]:
        """右侧：从订单的逐晚快照重新加总（含已退房），**不读库存表**。"""
        sql = (
            "SELECT b.booking_no AS booking_no, b.room_type_id AS room_type_id, "
            "n.stay_date AS stay_date, n.room_count AS room_count "
            "FROM booking_night n JOIN booking b ON b.id = n.booking_id "
            f"WHERE b.status IN ({OCCUPYING_PLACEHOLDERS}) "
            "AND n.stay_date >= ? AND n.stay_date < ? "
        )
        params: list[object] = [*OCCUPYING_VALUES, date_text(start), date_text(end)]
        if hotel_id is not None:
            sql += "AND b.hotel_id = ? "
            params.append(hotel_id)
        sql += "ORDER BY b.room_type_id, n.stay_date, b.booking_no"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            OrderNightRow(
                booking_no=str(row["booking_no"]),
                room_type_id=int(row["room_type_id"]),
                stay_date=str(row["stay_date"]),
                room_count=int(row["room_count"]),
            )
            for row in rows
        ]
