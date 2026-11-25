"""酒店 / 房型 / 账号的只读查询（界面层取数用，全部 SELECT，不写业务规则）。

为什么单独一个文件：``catalog_repository.py`` 只负责"下单要用的价格"和"认人"，
而界面还要"搜酒店、看房型、看审核状态"。两类读模型诉求不同，混在一起会让
一个类既服务下单又服务列表页；拆开后每个类只有一种查询形状。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from app.infrastructure.db.mapping import date_text


@dataclass(frozen=True, slots=True)
class HotelRow:
    """酒店一行（含审核状态，平台管理页要用）。"""

    hotel_id: int
    name: str
    address: str
    phone: str
    description: str | None
    audit_status: str
    reject_reason: str | None


@dataclass(frozen=True, slots=True)
class RoomTypeRow:
    """房型一行。"""

    room_type_id: int
    hotel_id: int
    name: str
    bed_type: str
    area_sqm: int
    capacity: int
    total_rooms: int


@dataclass(frozen=True, slots=True)
class AccountRow:
    """账号一行（不含密码散列，界面不需要）。"""

    account_id: int
    login_name: str
    role: str
    hotel_id: int | None
    status: str


class SqliteCatalogQueryRepository:
    """酒店与房型的只读查询。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def search_hotels(self, keyword: str | None = None) -> list[HotelRow]:
        """只返回已审核通过的酒店；关键词同时匹配名称与地址。"""
        sql = (
            "SELECT id, name, address, phone, description, audit_status, reject_reason "
            "FROM hotel WHERE audit_status = 'APPROVED'"
        )
        params: list[object] = []
        if keyword:
            sql += " AND (name LIKE ? OR address LIKE ?)"
            like = f"%{keyword.strip()}%"
            params = [like, like]
        sql += " ORDER BY id"
        return [_hotel_row(row) for row in self._conn.execute(sql, params).fetchall()]

    def all_hotels(self, audit_status: str | None = None) -> list[HotelRow]:
        """平台管理页用：可只看某一审核状态。"""
        sql = (
            "SELECT id, name, address, phone, description, audit_status, reject_reason "
            "FROM hotel"
        )
        params: list[object] = []
        if audit_status:
            sql += " WHERE audit_status = ?"
            params = [audit_status]
        sql += " ORDER BY id"
        return [_hotel_row(row) for row in self._conn.execute(sql, params).fetchall()]

    def hotel(self, hotel_id: int) -> HotelRow | None:
        """按主键取酒店。"""
        row = self._conn.execute(
            "SELECT id, name, address, phone, description, audit_status, reject_reason "
            "FROM hotel WHERE id = ?",
            (hotel_id,),
        ).fetchone()
        return None if row is None else _hotel_row(row)

    def room_types(self, hotel_id: int) -> list[RoomTypeRow]:
        """某酒店的房型（按主键，界面展示顺序稳定）。"""
        rows = self._conn.execute(
            "SELECT id, hotel_id, name, bed_type, area_sqm, capacity, total_rooms "
            "FROM room_type WHERE hotel_id = ? ORDER BY id",
            (hotel_id,),
        ).fetchall()
        return [_room_type_row(row) for row in rows]

    def room_type(self, room_type_id: int) -> RoomTypeRow | None:
        """按主键取房型。"""
        row = self._conn.execute(
            "SELECT id, hotel_id, name, bed_type, area_sqm, capacity, total_rooms "
            "FROM room_type WHERE id = ?",
            (room_type_id,),
        ).fetchone()
        return None if row is None else _room_type_row(row)

    def min_price_cents(self, room_type_id: int, dates: Sequence[date]) -> int | None:
        """区间最低单价；一天都没配价时返回 None（界面显示"待配价"）。"""
        if not dates:
            return None
        placeholders = ",".join("?" for _ in dates)
        row = self._conn.execute(
            "SELECT MIN(unit_price_cents) AS lowest FROM room_price "
            f"WHERE room_type_id = ? AND stay_date IN ({placeholders})",
            (room_type_id, *[date_text(day) for day in dates]),
        ).fetchone()
        lowest = None if row is None else row["lowest"]
        return None if lowest is None else int(lowest)

    def accounts(self, role: str | None = None) -> list[AccountRow]:
        """平台管理页用：账号列表（不含密码散列）。"""
        sql = "SELECT id, login_name, role, hotel_id, status FROM user_account"
        params: list[object] = []
        if role:
            sql += " WHERE role = ?"
            params = [role]
        sql += " ORDER BY id"
        return [
            AccountRow(
                account_id=int(row["id"]),
                login_name=str(row["login_name"]),
                role=str(row["role"]),
                hotel_id=None if row["hotel_id"] is None else int(row["hotel_id"]),
                status=str(row["status"]),
            )
            for row in self._conn.execute(sql, params).fetchall()
        ]


def _hotel_row(row: sqlite3.Row) -> HotelRow:
    return HotelRow(
        hotel_id=int(row["id"]),
        name=str(row["name"]),
        address=str(row["address"]),
        phone=str(row["phone"]),
        description=None if row["description"] is None else str(row["description"]),
        audit_status=str(row["audit_status"]),
        reject_reason=None if row["reject_reason"] is None else str(row["reject_reason"]),
    )


def _room_type_row(row: sqlite3.Row) -> RoomTypeRow:
    return RoomTypeRow(
        room_type_id=int(row["id"]),
        hotel_id=int(row["hotel_id"]),
        name=str(row["name"]),
        bed_type=str(row["bed_type"]),
        area_sqm=int(row["area_sqm"]),
        capacity=int(row["capacity"]),
        total_rooms=int(row["total_rooms"]),
    )
