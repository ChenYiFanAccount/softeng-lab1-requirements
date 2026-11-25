"""``booking`` / ``booking_night`` 的 SQLite 仓储实现。

三条要点：

1. **写操作必须已在外层 ``BEGIN IMMEDIATE`` 事务里**。本类不开事务、不提交，
   事务边界由应用服务掌握（这样"复核重复 → 改占用 → 建单 → 写审计"才能同生共死）。
2. ``save`` 对订单主体与逐晚快照做"主体 upsert + 快照整删整插"，因为逐晚快照
   完全由（起止日、单价、间数）派生，重算比增量维护更不容易出错。
3. ``find_active_overlap`` 用**区间相交**判断：``旧.入住 < 新.退房 且 旧.退房 > 新.入住``，
   且只比对有效状态（待确认/已确认/已入住）。U6 部分唯一索引只能拦"起止日完全相同"，
   区间重叠必须在这里查。
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Sequence

from app.domain.enums import BookingStatus
from app.domain.models import Booking, BookingNight
from app.domain.repositories import BookingRepository
from app.infrastructure.db.mapping import date_text, parse_date, parse_time, time_text

#: 有效状态：占着库存、参与重复预订判定
ACTIVE_STATUS_SQL = "('PENDING', 'CONFIRMED', 'CHECKED_IN')"

_BOOKING_COLUMNS = (
    "id, booking_no, guest_id, hotel_id, room_type_id, room_count, "
    "check_in_date, check_out_date, total_price_cents, status, idempotency_key, "
    "cancel_reason, cancel_initiator, created_at, updated_at"
)


def _to_night(row: sqlite3.Row) -> BookingNight:
    return BookingNight(
        booking_id=int(row["booking_id"]),
        stay_date=parse_date(row["stay_date"]),
        unit_price_cents=int(row["unit_price_cents"]),
        room_count=int(row["room_count"]),
    )


def _to_booking(row: sqlite3.Row, nights: Sequence[BookingNight]) -> Booking:
    return Booking(
        booking_no=str(row["booking_no"]),
        guest_id=int(row["guest_id"]),
        hotel_id=int(row["hotel_id"]),
        room_type_id=int(row["room_type_id"]),
        check_in_date=parse_date(row["check_in_date"]),
        check_out_date=parse_date(row["check_out_date"]),
        room_count=int(row["room_count"]),
        total_price_cents=int(row["total_price_cents"]),
        status=BookingStatus(str(row["status"])),
        booking_id=int(row["id"]),
        idempotency_key=row["idempotency_key"],
        cancel_reason=row["cancel_reason"],
        cancel_initiator=row["cancel_initiator"],
        created_at=parse_time(row["created_at"]),
        updated_at=parse_time(row["updated_at"]),
        nights=list(nights),
    )


class SqliteBookingRepository(BookingRepository):
    """订单仓储：读写 ``booking`` 与 ``booking_night``。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def nights_of(self, booking_id: int) -> list[BookingNight]:
        """按日期升序取某订单的逐晚快照。"""
        rows = self._conn.execute(
            "SELECT booking_id, stay_date, unit_price_cents, room_count "
            "FROM booking_night WHERE booking_id = ? ORDER BY stay_date",
            (booking_id,),
        ).fetchall()
        return [_to_night(row) for row in rows]

    def get_by_no(self, booking_no: str) -> Booking | None:
        """按订单号取订单（含逐晚快照）；不存在返回 None。"""
        row = self._conn.execute(
            f"SELECT {_BOOKING_COLUMNS} FROM booking WHERE booking_no = ?",
            (booking_no,),
        ).fetchone()
        if row is None:
            return None
        return _to_booking(row, self.nights_of(int(row["id"])))

    def find_active_overlap(
        self,
        guest_id: int,
        hotel_id: int,
        room_type_id: int,
        check_in_date: date,
        check_out_date: date,
    ) -> Booking | None:
        """查"同顾客 + 同酒店 + 同房型 + 日期区间相交"的有效订单。"""
        row = self._conn.execute(
            f"SELECT {_BOOKING_COLUMNS} FROM booking "
            f"WHERE guest_id = ? AND hotel_id = ? AND room_type_id = ? "
            f"AND status IN {ACTIVE_STATUS_SQL} "
            "AND check_in_date < ? AND check_out_date > ? "
            "ORDER BY check_in_date LIMIT 1",
            (guest_id, hotel_id, room_type_id, date_text(check_out_date), date_text(check_in_date)),
        ).fetchone()
        if row is None:
            return None
        return _to_booking(row, self.nights_of(int(row["id"])))

    def list_by_guest(self, guest_id: int, limit: int = 100) -> list[Booking]:
        """顾客的订单列表（新单在前），界面"我的订单"用。"""
        rows = self._conn.execute(
            f"SELECT {_BOOKING_COLUMNS} FROM booking WHERE guest_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (guest_id, limit),
        ).fetchall()
        return [_to_booking(row, self.nights_of(int(row["id"]))) for row in rows]

    def list_by_hotel(self, hotel_id: int, limit: int = 200) -> list[Booking]:
        """酒店的订单台列表（新单在前）。"""
        rows = self._conn.execute(
            f"SELECT {_BOOKING_COLUMNS} FROM booking WHERE hotel_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (hotel_id, limit),
        ).fetchall()
        return [_to_booking(row, self.nights_of(int(row["id"]))) for row in rows]

    def save(self, booking: Booking) -> Booking:
        """插入或更新订单主体，并把逐晚快照重写一遍；返回带主键的对象。"""
        now = time_text(booking.updated_at)
        if booking.booking_id is None:
            cursor = self._conn.execute(
                "INSERT INTO booking (booking_no, guest_id, hotel_id, room_type_id, room_count, "
                "check_in_date, check_out_date, total_price_cents, status, idempotency_key, "
                "cancel_reason, cancel_initiator, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    booking.booking_no,
                    booking.guest_id,
                    booking.hotel_id,
                    booking.room_type_id,
                    booking.room_count,
                    date_text(booking.check_in_date),
                    date_text(booking.check_out_date),
                    booking.total_price_cents,
                    booking.status.value,
                    booking.idempotency_key,
                    booking.cancel_reason,
                    booking.cancel_initiator,
                    time_text(booking.created_at),
                    now,
                ),
            )
            booking.booking_id = int(cursor.lastrowid)
        else:
            self._conn.execute(
                "UPDATE booking SET room_count = ?, check_in_date = ?, check_out_date = ?, "
                "total_price_cents = ?, status = ?, cancel_reason = ?, cancel_initiator = ?, "
                "updated_at = ? WHERE id = ?",
                (
                    booking.room_count,
                    date_text(booking.check_in_date),
                    date_text(booking.check_out_date),
                    booking.total_price_cents,
                    booking.status.value,
                    booking.cancel_reason,
                    booking.cancel_initiator,
                    now,
                    booking.booking_id,
                ),
            )
        self._replace_nights(booking)
        return booking

    def _replace_nights(self, booking: Booking) -> None:
        """整删整插逐晚快照（快照是派生数据，重算最稳）。"""
        self._conn.execute("DELETE FROM booking_night WHERE booking_id = ?", (booking.booking_id,))
        for night in booking.nights:
            self._conn.execute(
                "INSERT INTO booking_night (booking_id, stay_date, unit_price_cents, room_count) "
                "VALUES (?, ?, ?, ?)",
                (
                    booking.booking_id,
                    date_text(night.stay_date),
                    night.unit_price_cents,
                    night.room_count,
                ),
            )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def insert_stay_record(
        self,
        booking_id: int,
        action: str,
        operator_id: int,
        source: str,
        at_text: str,
        remark: str | None = None,
    ) -> None:
        """写一条入住/退房/未到店记录（``stay_record``）。"""
        self._conn.execute(
            "INSERT INTO stay_record (booking_id, action, operator_id, source, remark, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (booking_id, action, operator_id, source, remark, at_text),
        )
