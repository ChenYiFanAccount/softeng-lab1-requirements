"""余量只读查询（全系统唯一一套口径，对应 03_数据设计.md §5）。

- 余量 = 可售间数 − 已占用间数，**派生不落库**；
- 区间可订上限 = 区间内各日余量的最小值（任一天为 0 或停售则整体不可订）；
- 界面同时并列显示可售 / 占用 / 余量三个数，不用「总房量 − 可售」反推占用。

日期的包含关系遵循订单语义：``[start_date, end_date)``，退房日当天不占库存。
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta


def date_range(start_date: date, end_date: date) -> list[date]:
    """返回 ``[start_date, end_date)`` 的逐日列表；起始不早于结束则为空。"""
    days: list[date] = []
    cursor = start_date
    while cursor < end_date:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def daily_rows(
    conn: sqlite3.Connection, room_type_id: int, start_date: date, end_date: date
) -> list[dict[str, object]]:
    """逐日取「可售 / 占用 / 余量 / 销售状态」，缺失的日期记 ``None``。

    Args:
        conn: 数据库连接。
        room_type_id: 房型主键。
        start_date: 入住日（含）。
        end_date: 退房日（不含）。

    Returns:
        每天一条记录，键为 ``stay_date`` / ``available_rooms`` / ``occupied_rooms`` /
        ``remaining`` / ``sale_status``；无库存行时前四项为 ``None``、状态为 ``MISSING``。
    """
    rows: list[dict[str, object]] = []
    for day in date_range(start_date, end_date):
        stay = day.isoformat()
        record = conn.execute(
            "SELECT available_rooms, occupied_rooms, sale_status FROM room_inventory"
            " WHERE room_type_id = ? AND stay_date = ?",
            (room_type_id, stay),
        ).fetchone()
        if record is None:
            rows.append(
                {
                    "stay_date": stay,
                    "available_rooms": None,
                    "occupied_rooms": None,
                    "remaining": None,
                    "sale_status": "MISSING",
                }
            )
            continue
        available = int(record["available_rooms"])
        occupied = int(record["occupied_rooms"])
        rows.append(
            {
                "stay_date": stay,
                "available_rooms": available,
                "occupied_rooms": occupied,
                "remaining": available - occupied,
                "sale_status": str(record["sale_status"]),
            }
        )
    return rows


def daily_remaining(
    conn: sqlite3.Connection, room_type_id: int, start_date: date, end_date: date
) -> dict[str, int]:
    """逐日余量字典（缺行日期不出现在结果里，由调用方决定如何提示）。

    Returns:
        键为 ``YYYY-MM-DD``、值为余量间数。S1-5 的用例对这张字典做硬编码断言。
    """
    return {
        str(row["stay_date"]): int(row["remaining"])  # type: ignore[arg-type]
        for row in daily_rows(conn, room_type_id, start_date, end_date)
        if row["remaining"] is not None
    }


def range_limit(
    conn: sqlite3.Connection, room_type_id: int, start_date: date, end_date: date
) -> int:
    """区间可订上限 = 区间内各日余量最小值；停售或缺行按 0 处理。

    Args:
        conn: 数据库连接。
        room_type_id: 房型主键。
        start_date: 入住日（含）。
        end_date: 退房日（不含，必须晚于入住日）。

    Returns:
        可订间数上限；区间为空时返回 0。
    """
    if end_date <= start_date:
        return 0
    limit: int | None = None
    for row in daily_rows(conn, room_type_id, start_date, end_date):
        if row["sale_status"] != "ON_SALE" or row["remaining"] is None:
            return 0
        remaining = int(row["remaining"])  # type: ignore[arg-type]
        limit = remaining if limit is None else min(limit, remaining)
    return limit or 0


def availability_summary(
    conn: sqlite3.Connection, room_type_id: int, start_date: date, end_date: date
) -> dict[str, object]:
    """汇总一行「区间可订上限 + 逐日明细」，供搜索结果页与订单详情页复用。"""
    rows = daily_rows(conn, room_type_id, start_date, end_date)
    return {
        "room_type_id": room_type_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "limit": range_limit(conn, room_type_id, start_date, end_date),
        "nights": len(rows),
        "daily": rows,
    }
