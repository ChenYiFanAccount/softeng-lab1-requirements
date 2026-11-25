"""种子数据：3 家酒店 / 8 个房型 / 90 天库存与价格 / 4 个账号 / 节假日。

规模由 S1-4 判据钉死：``hotel=3 room_type=8 room_inventory=720 room_price=720
user_account>=4 holiday_calendar>=1``。720 = 8 房型 × 90 天，因此库存与价格表
的行数是房型数与天数之积，改动任一常量都要同步改 ``交付/S1/交付说明.md``。

全部数据确定性生成（无随机数、无 ``now()`` 参与的取值范围），同一脚本跑两遍
得到同一份库；时间戳用 UTC 秒级文本，仅作记录，不参与断言。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.domain.enums import SYSTEM_ACCOUNT_ID as _SYSTEM_ACCOUNT_ID
from app.infrastructure.db.connection import immediate_transaction
from app.infrastructure.security import derive_salt, hash_password

#: 演示口令（报告与 README 公开说明；真实系统不得硬编码）
DEMO_PASSWORD = "Passw0rd!"

#: 库存 / 价格滚动天数
HORIZON_DAYS = 90

#: 酒店种子：名称、地址、电话、简介、审核状态
HOTELS: tuple[tuple[str, str, str, str, str], ...] = (
    ("云栖酒店", "杭州市西湖区云栖路 18 号", "0571-88000001", "西湖景区内的庭院式酒店", "APPROVED"),
    ("江畔假日酒店", "南京市建邺区江东中路 100 号", "025-66000002", "临江高层，商务出行首选", "APPROVED"),
    ("山间小筑", "湖州市德清县莫干山路 7 号", "0572-88000003", "竹林深处的民宿式度假屋", "PENDING"),
)

#: 房型种子：酒店序号、名称、床型、面积、可住人数、总房量、基础价（分/晚）
ROOM_TYPES: tuple[tuple[int, str, str, int, int, int, int], ...] = (
    (1, "云栖大床房", "大床 1.8m", 28, 2, 10, 29900),
    (1, "云栖双床房", "双床 1.2m", 32, 2, 8, 32900),
    (1, "云栖家庭房", "大床 + 单床", 45, 4, 6, 45900),
    (2, "江畔大床房", "大床 1.8m", 30, 2, 12, 31900),
    (2, "江畔双床房", "双床 1.2m", 34, 2, 9, 34900),
    (2, "江畔行政套房", "大床 + 客厅", 55, 3, 5, 59900),
    (3, "山间大床房", "大床 1.5m", 26, 2, 7, 26900),
    (3, "山间复式房", "上下两层", 60, 4, 4, 49900),
)

#: 账号种子：登录名、角色、所属酒店序号（None 表示无）、状态
ACCOUNTS: tuple[tuple[str, str, int | None, str], ...] = (
    ("13800000000", "PLATFORM_ADMIN", None, "ACTIVE"),
    ("13800000001", "CUSTOMER", None, "ACTIVE"),
    ("13800000002", "HOTEL_STAFF", 1, "ACTIVE"),
    ("13800000003", "HOTEL_STAFF", 2, "ACTIVE"),
)

#: 系统服务账号的固定主键（见 :func:`_insert_accounts` 的说明）
SYSTEM_ACCOUNT_ID = _SYSTEM_ACCOUNT_ID

#: 周末加价（周五、周六入住晚）
WEEKEND_SURCHARGE_CENTS = 5000

#: 节假日加价
HOLIDAY_SURCHARGE_CENTS = 8000


@dataclass
class SeedOutcome:
    """种子执行结果。"""

    applied: bool
    counts: dict[str, int] = field(default_factory=dict)


def now_text() -> str:
    """当前 UTC 时间，``YYYY-MM-DD HH:MM:SS``。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def date_range(start: date, days: int) -> list[date]:
    """返回从 ``start`` 起连续 ``days`` 天（含首日）。"""
    return [start + timedelta(days=offset) for offset in range(days)]


def daily_price_cents(base_cents: int, stay_date: date, holidays: set[str]) -> int:
    """按「基础价 + 周末/节假日加价」算某一天的挂牌单价（整数分）。"""
    price = base_cents
    if stay_date.weekday() in (4, 5):  # 周五、周六
        price += WEEKEND_SURCHARGE_CENTS
    if stay_date.isoformat() in holidays:
        price += HOLIDAY_SURCHARGE_CENTS
    return price


def seed_all(conn: sqlite3.Connection, settings: dict[str, Any] | None = None) -> SeedOutcome:
    """写入种子数据；库中已有酒店行时跳过（幂等）。

    Args:
        conn: 已迁移到最新版本的连接。
        settings: 可选的配置字典（取 ``seed.horizon_days`` 与 ``seed.holidays``）。

    Returns:
        是否实际写入，以及写入后的行数快照。
    """
    settings = settings or {}
    if _count(conn, "hotel") > 0:
        return SeedOutcome(applied=False, counts=_snapshot(conn))

    horizon = int(settings.get("seed", {}).get("horizon_days", HORIZON_DAYS))
    holidays = _holiday_rows(settings)
    today = date.today()

    with immediate_transaction(conn):
        hotel_ids = _insert_hotels(conn)
        room_type_ids, prices = _insert_room_types(conn, hotel_ids)
        _insert_inventory_and_prices(
            conn,
            room_type_ids=room_type_ids,
            base_prices=prices,
            days=date_range(today, horizon),
            holidays={row[0] for row in holidays},
        )
        _insert_accounts(conn, hotel_ids)
        _insert_holidays(conn, holidays)
    return SeedOutcome(applied=True, counts=_snapshot(conn))


def clear_all(conn: sqlite3.Connection) -> None:
    """按外键依赖倒序清空全部业务表（``--reset`` 用）。"""
    tables = (
        "booking_night",
        "stay_record",
        "notification_record",
        "booking",
        "idempotency_key",
        "room_inventory",
        "room_price",
        "room_type",
        "user_account",
        "hotel",
        "holiday_calendar",
        "audit_log",
    )
    with immediate_transaction(conn):
        for table in tables:
            conn.execute(f'DELETE FROM "{table}"')
        conn.execute("DELETE FROM sqlite_sequence")


def _insert_hotels(conn: sqlite3.Connection) -> dict[int, int]:
    """写入 3 家酒店，返回「种子序号 → 实际主键」。"""
    ids: dict[int, int] = {}
    stamp = now_text()
    for index, (name, address, phone, description, audit_status) in enumerate(HOTELS, start=1):
        audited_at = stamp if audit_status != "PENDING" else None
        cursor = conn.execute(
            "INSERT INTO hotel (name, address, phone, description, audit_status,"
            " reject_reason, created_at, audited_at)"
            " VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
            (name, address, phone, description, audit_status, stamp, audited_at),
        )
        ids[index] = int(cursor.lastrowid)
    return ids


def _insert_room_types(
    conn: sqlite3.Connection, hotel_ids: dict[int, int]
) -> tuple[dict[int, int], dict[int, int]]:
    """写入 8 个房型，返回「种子序号 → 主键」与「主键 → 基础价」。"""
    ids: dict[int, int] = {}
    base_prices: dict[int, int] = {}
    for index, (hotel_index, name, bed_type, area, capacity, total_rooms, base) in enumerate(
        ROOM_TYPES, start=1
    ):
        cursor = conn.execute(
            "INSERT INTO room_type (hotel_id, name, bed_type, area_sqm, capacity, total_rooms)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (hotel_ids[hotel_index], name, bed_type, area, capacity, total_rooms),
        )
        room_type_id = int(cursor.lastrowid)
        ids[index] = room_type_id
        base_prices[room_type_id] = base
    return ids, base_prices


def _insert_inventory_and_prices(
    conn: sqlite3.Connection,
    *,
    room_type_ids: dict[int, int],
    base_prices: dict[int, int],
    days: list[date],
    holidays: set[str],
) -> None:
    """逐「房型 × 日期」写库存与价格；可售 = 总房量，占用 = 0。"""
    stamp = now_text()
    totals = {index: row[5] for index, row in enumerate(ROOM_TYPES, start=1)}
    for index, room_type_id in room_type_ids.items():
        total_rooms = totals[index]
        for stay_date in days:
            stay = stay_date.isoformat()
            conn.execute(
                "INSERT INTO room_inventory (room_type_id, stay_date, available_rooms,"
                " occupied_rooms, sale_status, updated_at)"
                " VALUES (?, ?, ?, 0, 'ON_SALE', ?)",
                (room_type_id, stay, total_rooms, stamp),
            )
            conn.execute(
                "INSERT INTO room_price (room_type_id, stay_date, unit_price_cents, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    room_type_id,
                    stay,
                    daily_price_cents(base_prices[room_type_id], stay_date, holidays),
                    stamp,
                ),
            )


def _insert_accounts(conn: sqlite3.Connection, hotel_ids: dict[int, int]) -> None:
    """写入系统服务账号与 4 个演示账号，口令统一为 :data:`DEMO_PASSWORD`。

    系统服务账号（``id = 0``、登录名 ``system``）供调度器写 ``stay_record`` 用：
    该表的 ``operator_id`` 是指向 ``user_account`` 的 NOT NULL 外键，系统动作必须
    有一个"真实存在的操作者"落库，否则外键会拒。它的 ``password_hash`` 被固定为
    ``"!"``（不是合法口令格式），因此**无法登录**，只作为系统动作的落点。
    """
    stamp = now_text()
    conn.execute(
        "INSERT INTO user_account (id, login_name, password_hash, role, hotel_id,"
        " status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (SYSTEM_ACCOUNT_ID, "system", "!", "PLATFORM_ADMIN", None, "ACTIVE", stamp),
    )
    for login_name, role, hotel_index, status in ACCOUNTS:
        hotel_id = hotel_ids[hotel_index] if hotel_index is not None else None
        conn.execute(
            "INSERT INTO user_account (login_name, password_hash, role, hotel_id,"
            " status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                login_name,
                hash_password(DEMO_PASSWORD, derive_salt(login_name)),
                role,
                hotel_id,
                status,
                stamp,
            ),
        )


def _insert_holidays(conn: sqlite3.Connection, holidays: list[tuple[str, str]]) -> None:
    """写入节假日日期表（状态默认启用）。"""
    for holiday_date, name in holidays:
        conn.execute(
            "INSERT INTO holiday_calendar (holiday_date, name, status) VALUES (?, ?, 'ENABLED')",
            (holiday_date, name),
        )


def _holiday_rows(settings: dict[str, Any]) -> list[tuple[str, str]]:
    """从配置里取节假日；缺省时给一天兜底，保证 ``holiday_calendar>=1``。"""
    configured = settings.get("seed", {}).get("holidays") or []
    rows = [(item["date"], item.get("name", "")) for item in configured if item.get("date")]
    return rows or [("2027-01-01", "元旦")]


def _count(conn: sqlite3.Connection, table: str) -> int:
    """统计单表行数。"""
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _snapshot(conn: sqlite3.Connection) -> dict[str, int]:
    """S1-4 断言的六张表行数快照。"""
    tables = (
        "hotel",
        "room_type",
        "room_inventory",
        "room_price",
        "user_account",
        "holiday_calendar",
    )
    return {table: _count(conn, table) for table in tables}
