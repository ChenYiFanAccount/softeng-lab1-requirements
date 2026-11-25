"""``room_inventory`` 的 SQLite 仓储实现（读余量、改占用、调可售）。

为什么占用增减只用一条 ``UPDATE ... SET occupied_rooms = occupied_rooms + ?``：
把"读-判断-写"压成数据库内的原子自增，配合外层 ``BEGIN IMMEDIATE`` 的单写者
语义，200 线程压测才不会出现两人读到同一余量后各写一次的情况（S3-2）。

行内 CHECK ``occupied_rooms <= available_rooms`` 与 ``occupied_rooms >= 0``
是最后一道闸：应用层算错时由数据库抛 ``IntegrityError``，而不是悄悄写坏数据。
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Sequence

from app.domain.errors import NoAvailabilityError
from app.domain.models import RoomInventory
from app.domain.repositories import InventoryRepository
from app.infrastructure.db.mapping import date_text, parse_date, parse_time, time_text


def _to_inventory(row: sqlite3.Row) -> RoomInventory:
    return RoomInventory(
        room_type_id=int(row["room_type_id"]),
        stay_date=parse_date(row["stay_date"]),
        available_rooms=int(row["available_rooms"]),
        occupied_rooms=int(row["occupied_rooms"]),
        sale_status=str(row["sale_status"]),
        updated_at=parse_time(row["updated_at"]),
    )


class SqliteInventoryRepository(InventoryRepository):
    """库存仓储：只碰 ``room_inventory``，不改订单。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def lock_rows(self, room_type_id: int, dates: Sequence[date]) -> list[RoomInventory]:
        """取指定日期区间的库存行（按日期升序）。

        注意：SQLite 没有 ``SELECT ... FOR UPDATE``；真正的写锁由外层
        ``BEGIN IMMEDIATE`` 在事务开始时一次性拿到，所以这里只是"在锁内读"。
        """
        if not dates:
            return []
        placeholders = ",".join("?" for _ in dates)
        rows = self._conn.execute(
            "SELECT room_type_id, stay_date, available_rooms, occupied_rooms, sale_status, "
            f"updated_at FROM room_inventory "
            f"WHERE room_type_id = ? AND stay_date IN ({placeholders}) "
            "ORDER BY stay_date",
            (room_type_id, *[date_text(day) for day in dates]),
        ).fetchall()
        return [_to_inventory(row) for row in rows]

    def add_occupied(self, room_type_id: int, stay_date: date, delta: int) -> int:
        """原子增减某日占用量，返回改后的占用值。

        Raises:
            NoAvailabilityError: 该日库存行不存在（说明日历没铺满）。
            sqlite3.IntegrityError: 改完会越界（占用 < 0 或占用 > 可售）。
        """
        cursor = self._conn.execute(
            "UPDATE room_inventory SET occupied_rooms = occupied_rooms + ?, updated_at = ? "
            "WHERE room_type_id = ? AND stay_date = ?",
            (delta, time_text(None), room_type_id, date_text(stay_date)),
        )
        if cursor.rowcount == 0:
            raise NoAvailabilityError(
                "该日期没有库存记录，无法占用",
                room_type_id=room_type_id,
                stay_date=date_text(stay_date),
            )
        row = self._conn.execute(
            "SELECT occupied_rooms FROM room_inventory WHERE room_type_id = ? AND stay_date = ?",
            (room_type_id, date_text(stay_date)),
        ).fetchone()
        return int(row["occupied_rooms"])

    def range_remaining(self, room_type_id: int, dates: Sequence[date]) -> dict[str, int]:
        """逐日余量（可售 − 占用）；缺行或停售记 0。"""
        result: dict[str, int] = {}
        for inventory in self.lock_rows(room_type_id, dates):
            key = date_text(inventory.stay_date)
            result[key] = inventory.remaining if inventory.is_on_sale else 0
        for day in dates:
            result.setdefault(date_text(day), 0)
        return result

    def set_available(self, room_type_id: int, stay_date: date, available_rooms: int) -> None:
        """调整某日可售房量（调用方须保证 ``available_rooms >= 已占用``）。"""
        self._conn.execute(
            "UPDATE room_inventory SET available_rooms = ?, updated_at = ? "
            "WHERE room_type_id = ? AND stay_date = ?",
            (available_rooms, time_text(None), room_type_id, date_text(stay_date)),
        )

    def set_sale_status(self, room_type_id: int, stay_date: date, sale_status: str) -> None:
        """设置某日销售状态（``ON_SALE`` / ``SUSPENDED``）。"""
        self._conn.execute(
            "UPDATE room_inventory SET sale_status = ?, updated_at = ? "
            "WHERE room_type_id = ? AND stay_date = ?",
            (sale_status, time_text(None), room_type_id, date_text(stay_date)),
        )

    def occupied_of(self, room_type_id: int, dates: Sequence[date]) -> dict[str, int]:
        """逐日占用量（测试断言用）。"""
        result = {date_text(day): 0 for day in dates}
        for inventory in self.lock_rows(room_type_id, dates):
            result[date_text(inventory.stay_date)] = inventory.occupied_rooms
        return result
