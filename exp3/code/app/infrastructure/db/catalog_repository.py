"""``room_price`` 与 ``user_account`` 的只读仓储（应用层拿价、认人用）。

为什么不放进领域层的 ``repositories.py``：类图只登记了三个仓储接口
（订单/库存/审计），价格与账号是"读配置"而不是业务聚合的持久化入口，
放基础设施层不会影响 S2-6 的 19 符号对齐（多出的类只进 ``extra_in_code``）。
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Sequence

from app.application.actor import Actor
from app.domain.errors import ValidationError
from app.infrastructure.db.mapping import date_text, parse_date, time_text


class SqlitePriceRepository:
    """按"房型 × 日期"读单价；缺价是**配置缺失**，属 422 而不是"无房"。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def nightly_prices(self, room_type_id: int, dates: Sequence[date]) -> dict[date, int]:
        """逐日单价（整数分）；缺任何一天就抛 422 并指出是哪天。"""
        if not dates:
            return {}
        placeholders = ",".join("?" for _ in dates)
        rows = self._conn.execute(
            "SELECT stay_date, unit_price_cents FROM room_price "
            f"WHERE room_type_id = ? AND stay_date IN ({placeholders})",
            (room_type_id, *[date_text(day) for day in dates]),
        ).fetchall()
        found = {parse_date(row["stay_date"]): int(row["unit_price_cents"]) for row in rows}
        for day in dates:
            if day not in found:
                raise ValidationError(
                    "该日期尚未配置房价，无法下单",
                    room_type_id=room_type_id,
                    stay_date=date_text(day),
                )
        return found

    def upsert(self, room_type_id: int, stay_date: date, unit_price_cents: int) -> None:
        """写入/覆盖某日单价（界面"库存与价格"页用）。"""
        if unit_price_cents <= 0:
            raise ValidationError("单价必须大于 0", unit_price_cents=unit_price_cents)
        self._conn.execute(
            "INSERT INTO room_price (room_type_id, stay_date, unit_price_cents, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (room_type_id, stay_date) DO UPDATE SET "
            "unit_price_cents = excluded.unit_price_cents, updated_at = excluded.updated_at",
            (room_type_id, date_text(stay_date), unit_price_cents, time_text(None)),
        )


class SqliteAccountRepository:
    """账号只读查询：登录认人、取操作者身份。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, account_id: int) -> Actor | None:
        """按主键取操作者；不存在返回 None。"""
        row = self._conn.execute(
            "SELECT id, login_name, role, hotel_id FROM user_account WHERE id = ?",
            (account_id,),
        ).fetchone()
        return None if row is None else Actor.from_row(row)

    def find_by_login(self, login_name: str) -> dict[str, object] | None:
        """按手机号取账号（含密码散列，仅供登录校验）。"""
        row = self._conn.execute(
            "SELECT id, login_name, password_hash, role, hotel_id, status "
            "FROM user_account WHERE login_name = ?",
            (login_name,),
        ).fetchone()
        return None if row is None else dict(row)
