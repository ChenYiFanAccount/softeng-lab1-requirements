"""订单应用服务：事务边界、权限、幂等、单号生成都收在这里。

**与领域服务的分工**（G1-R1-05 要求写进 S3 交付说明）：

- 领域服务（``app/domain/services.py``）只管规则：能不能占、能不能转、算多少钱；
  **不碰事务、不碰幂等键、不生成单号**。
- 本类管流程：开 ``BEGIN IMMEDIATE``、按角色判可见性、按幂等键去重、生成单号、
  写审计，并在失败时整体回滚。

下单事务的固定顺序（对应 `02_模块划分与交互.md` 的"下单锁库存"链路）：

1. 查幂等键 —— 命中就直接返回原订单，不再建单；
2. 查同顾客同房型同时段的有效订单（区间相交，U6 索引只拦起止日相同）；
3. 锁内读余量并复核（缺行、停售、余量不足都在这里拒）；
4. 逐日 ``occupied_rooms += n``（数据库内原子自增）；
5. 建单 + 逐晚快照 + 幂等键 + 审计，同一事务提交。
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import date, datetime

from app.application.actor import Actor
from app.application.clock import Clock, SystemClock
from app.application.commands import PlaceBookingCommand, RescheduleCommand
from app.application.errors import ConflictError, masked_booking_error
from app.domain.enums import ActorRole, BookingEvent, BookingStatus
from app.domain.errors import (
    DomainError,
    DuplicateBookingError,
    IllegalTransitionError,
    NoAvailabilityError,
    PermissionDeniedError,
)
from app.domain.models import AuditLog, Booking
from app.domain.pricing import quote, stay_dates
from app.domain.state_machine import BookingStateMachine
from app.infrastructure.db.audit_repository import (
    SqliteAuditLogRepository,
    SqliteIdempotencyRepository,
)
from app.infrastructure.db.booking_repository import SqliteBookingRepository
from app.infrastructure.db.catalog_repository import SqlitePriceRepository
from app.infrastructure.db.connection import immediate_transaction
from app.infrastructure.db.inventory_repository import SqliteInventoryRepository
from app.infrastructure.db.mapping import date_text

#: 终止类事件：转过去就要把占用的房量放回
#: （``NO_SHOW`` 也算：客人没来，房间不该被"幽灵住宿"永久占住）
RELEASING_EVENTS = (
    BookingEvent.CANCEL,
    BookingEvent.REJECT,
    BookingEvent.TIMEOUT,
    BookingEvent.NO_SHOW,
)

#: 办理类事件：转过去要写一条 ``stay_record``
STAY_EVENTS = {
    BookingEvent.CHECK_IN: "CHECK_IN",
    BookingEvent.CHECK_OUT: "CHECK_OUT",
    BookingEvent.NO_SHOW: "NO_SHOW",
}

#: ``audit_log.operator_role`` 用的短码（与订单表 ``cancel_initiator`` 同词表）
AUDIT_ROLE_CODE = {
    ActorRole.CUSTOMER: "CUSTOMER",
    ActorRole.HOTEL_STAFF: "HOTEL",
    ActorRole.PLATFORM_ADMIN: "ADMIN",
    ActorRole.SYSTEM: "SYSTEM",
}

#: 被拒操作的审计前缀：403 记"无权"，409 记"被规则拒"，都带事件名
FAILED_ACTION_PREFIX = {403: "DENIED", 409: "REJECTED"}


class BookingAppService:  # pylint: disable=too-many-instance-attributes
    """订单应用服务：一个连接一组仓储，方法自身负责开/提交事务。

    六个仓储 + 连接 + 时钟 + 状态机 = 8 个属性，都是本类的固定协作者，
    拆成一个"依赖包"对象只会把参数列表从构造器挪到别处，可读性反而更差。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        clock: Clock | None = None,
        machine: BookingStateMachine | None = None,
    ) -> None:
        self._conn = conn
        self._clock: Clock = clock or SystemClock()
        self._machine = machine or BookingStateMachine()
        self._bookings = SqliteBookingRepository(conn)
        self._inventories = SqliteInventoryRepository(conn)
        self._prices = SqlitePriceRepository(conn)
        self._ids = SqliteIdempotencyRepository(conn)
        self._audits = SqliteAuditLogRepository(conn)

    # ------------------------------------------------------------------ 下单

    def place_booking(self, command: PlaceBookingCommand, actor: Actor | None = None) -> Booking:
        """下单：校验 → 复核重复与余量 → 占库 → 建单 → 审计（单事务）。

        Args:
            command: 下单命令（顾客、房型、起止日、间数、可选幂等键）。
            actor: 操作者；省略时按"顾客本人"处理。

        Returns:
            新建（或幂等命中时已存在）的订单。

        Raises:
            PermissionDeniedError: 替别人下单。
            DuplicateBookingError: 同时段已有有效订单。
            NoAvailabilityError: 停售、缺行或余量不足。
            ValidationError: 日期顺序、间数、缺价等入参问题。
        """
        operator = actor or Actor(command.guest_id, ActorRole.CUSTOMER)
        self._assert_can_book(operator, command.guest_id)
        dates = stay_dates(command.check_in_date, command.check_out_date)
        prices = self._prices.nightly_prices(command.room_type_id, dates)
        quotation = quote(
            prices,
            command.check_in_date,
            command.check_out_date,
            command.room_count,
        )
        booking_no = self._new_booking_no(self._clock.now())

        with immediate_transaction(self._conn):
            hit = self._idempotent_hit(command.idempotency_key)
            if hit is not None:
                return hit
            overlap = self._bookings.find_active_overlap(
                command.guest_id,
                command.hotel_id,
                command.room_type_id,
                command.check_in_date,
                command.check_out_date,
            )
            if overlap is not None:
                raise DuplicateBookingError(
                    "同一时段已有有效订单，不能重复预订",
                    booking_no=overlap.booking_no,
                    check_in_date=date_text(command.check_in_date),
                    check_out_date=date_text(command.check_out_date),
                )
            self._ensure_available(command.room_type_id, dates, command.room_count)
            for day in dates:
                self._inventories.add_occupied(command.room_type_id, day, command.room_count)
            booking = Booking(
                booking_no=booking_no,
                guest_id=command.guest_id,
                hotel_id=command.hotel_id,
                room_type_id=command.room_type_id,
                check_in_date=command.check_in_date,
                check_out_date=command.check_out_date,
                room_count=command.room_count,
                total_price_cents=quotation.total_cents,
                status=BookingStatus.PENDING,
                idempotency_key=command.idempotency_key,
                created_at=self._clock.now(),
                updated_at=self._clock.now(),
                nights=quotation.to_booking_nights(0),
            )
            if command.idempotency_key:
                self._ids.put(command.idempotency_key, booking_no)
            self._bookings.save(booking)
            self._write_audit(booking, "CREATE", operator, None, BookingStatus.PENDING)
            return booking

    # ------------------------------------------------------------------ 查询

    def get_booking(self, booking_no: str, actor: Actor) -> Booking:
        """按订单号取订单；看不见的订单与本就不存在的订单返回同一错误。"""
        return self._visible(booking_no, actor)

    def list_my_bookings(self, actor: Actor, limit: int = 100) -> list[Booking]:
        """顾客看自己的订单；管理员看全部（按创建时间倒序）。"""
        if actor.is_admin:
            return self._all_bookings(limit)
        return self._bookings.list_by_guest(actor.account_id, limit)

    def list_hotel_bookings(self, actor: Actor, hotel_id: int, limit: int = 200) -> list[Booking]:
        """酒店订单台：只能看自己酒店的订单。"""
        if not (actor.is_admin or actor.works_at(hotel_id)):
            raise masked_booking_error()
        return self._bookings.list_by_hotel(hotel_id, limit)

    def _all_bookings(self, limit: int) -> list[Booking]:
        """管理员视角：跨酒店取单（走 SQL 直查，避免为报表再开一个仓储接口）。"""
        rows = self._conn.execute(
            "SELECT booking_no FROM booking ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            booking = self._bookings.get_by_no(str(row["booking_no"]))
            if booking is not None:
                result.append(booking)
        return result

    # ------------------------------------------------------------------ 状态流转

    def apply_event(
        self,
        booking_no: str,
        event: BookingEvent,
        actor: Actor,
        reason: str | None = None,
    ) -> Booking:
        """执行一次状态流转：校验角色 → 改状态 → 释放库存 / 写住店记录 → 审计。

        Args:
            booking_no: 订单号。
            event: 领域事件（见 ``BookingEvent``）。
            actor: 操作者；角色不在该边的允许集合内会被拒（403）。
            reason: 取消/拒绝原因，写进 ``cancel_reason``。

        Returns:
            流转后的订单。

        Raises:
            IllegalTransitionError: 该边不允许（409），已在审计里留 ``REJECTED:<事件>``。
            PermissionDeniedError: 角色无权触发该边（403），审计留 ``DENIED:<事件>``。
        """
        failure: DomainError | None = None
        with immediate_transaction(self._conn):
            booking = self._visible(booking_no, actor)
            before = booking.status
            failure = self._transition_or_record(booking, event, actor, reason)
            if failure is None:
                self._finish_transition(booking, event, actor, reason, before)
        if failure is not None:
            raise failure
        return booking

    # ------------------------------------------------------------------ 流转内部步骤

    def _transition_or_record(
        self,
        booking: Booking,
        event: BookingEvent,
        actor: Actor,
        reason: str | None,
    ) -> DomainError | None:
        """尝试改状态；被状态机拒时先在事务内补一条失败审计，再把异常交回调用方。

        为什么要在同一个事务里写失败审计：审计表只追加，失败也是事实；若等
        回滚后再单独写，就变成"两次提交"，一旦进程在中间退出，失败记录会丢。
        """
        try:
            self._machine.transition(
                booking,
                event,
                role=actor.role,
                at=self._clock.now(),
                reason=reason,
            )
        except (IllegalTransitionError, PermissionDeniedError) as error:
            self._write_failed_audit(booking, event, actor, error)
            return error
        return None

    def _finish_transition(
        self,
        booking: Booking,
        event: BookingEvent,
        actor: Actor,
        reason: str | None,
        before: BookingStatus,
    ) -> None:
        """状态已经改好之后的收尾：释放库存、写住店记录、写审计。"""
        booking.cancel_initiator = (
            actor.initiator_code if event in RELEASING_EVENTS else booking.cancel_initiator
        )
        if event in RELEASING_EVENTS:
            self._release(booking)
        self._bookings.save(booking)
        stay_action = STAY_EVENTS.get(event)
        if stay_action is not None:
            self._bookings.insert_stay_record(
                booking.booking_id,
                stay_action,
                actor.account_id,
                "SYSTEM" if actor.is_system else "MANUAL",
                self._clock.now().strftime("%Y-%m-%d %H:%M:%S"),
                reason,
            )
        self._write_audit(booking, event.value, actor, before, booking.status, reason)

    def _write_failed_audit(
        self,
        booking: Booking,
        event: BookingEvent,
        actor: Actor,
        error: DomainError,
    ) -> None:
        """记录一次被拒的流转尝试（403 → ``DENIED:``，409 → ``REJECTED:``）。"""
        prefix = FAILED_ACTION_PREFIX.get(error.http_status, "FAILED")
        self._audits.append(
            AuditLog(
                operator_id=actor.account_id,
                operator_role=AUDIT_ROLE_CODE[actor.role],
                target_type="BOOKING",
                target_id=booking.booking_no,
                action=f"{prefix}:{event.value}",
                before_state=booking.status.value,
                after_state=booking.status.value,
                created_at=self._clock.now(),
            )
        )

    def cancel_booking(
        self,
        booking_no: str,
        actor: Actor,
        reason: str | None = None,
    ) -> Booking:
        """取消订单（T6 顾客/酒店/管理员；待确认单只能由酒店拒单或系统超时）。"""
        return self.apply_event(booking_no, BookingEvent.CANCEL, actor, reason)

    # ------------------------------------------------------------------ 改期

    def reschedule_booking(
        self,
        booking_no: str,
        command: RescheduleCommand,
        actor: Actor,
    ) -> Booking:
        """改期：**先占新、后放旧**，整体一个事务（失败则新日期占用自动回滚）。

        为什么重叠区间要先加回"自己占的那部分"：改到与旧区间相交的日期时，
        那些天的 ``occupied_rooms`` 本来就含本单，直接比余量会误判无房。

        Args:
            booking_no: 原订单号。
            command: 新日期区间。
            actor: 操作者（顾客本人 / 本酒店员工 / 管理员）。

        Returns:
            改期后的订单（逐晚快照与总价已重算）。

        Raises:
            ConflictError: 订单不是已确认状态。
            NoAvailabilityError: 新日期停售、缺行或有效余量不足。
        """
        with immediate_transaction(self._conn):
            booking = self._visible(booking_no, actor)
            if booking.status is not BookingStatus.CONFIRMED:
                raise ConflictError(
                    "只有已确认的订单可以改期",
                    booking_no=booking_no,
                    status=booking.status.value,
                )
            new_dates = stay_dates(command.new_check_in_date, command.new_check_out_date)
            prices = self._prices.nightly_prices(booking.room_type_id, new_dates)
            quotation = quote(
                prices,
                command.new_check_in_date,
                command.new_check_out_date,
                booking.room_count,
            )
            old_dates = list(booking.stay_dates)
            own_dates = set(old_dates)
            new_set = set(new_dates)
            self._ensure_reschedule_room(booking, new_dates, own_dates)
            for day in new_dates:
                if day not in own_dates:
                    self._inventories.add_occupied(booking.room_type_id, day, booking.room_count)
            for day in old_dates:
                if day not in new_set:
                    self._inventories.add_occupied(booking.room_type_id, day, -booking.room_count)
            before = f"{date_text(booking.check_in_date)}~{date_text(booking.check_out_date)}"
            booking.check_in_date = command.new_check_in_date
            booking.check_out_date = command.new_check_out_date
            booking.total_price_cents = quotation.total_cents
            booking.updated_at = self._clock.now()
            booking.nights = quotation.to_booking_nights(booking.booking_id or 0)
            self._bookings.save(booking)
            after = (
                f"{date_text(command.new_check_in_date)}"
                f"~{date_text(command.new_check_out_date)}"
            )
            self._write_audit(booking, "RESCHEDULE", actor, before, after, command.reason)
            return booking

    # ------------------------------------------------------------------ 内部工具

    def _idempotent_hit(self, key: str | None) -> Booking | None:
        """幂等键已登记过就返回原订单（必须在事务内调用）。"""
        if not key:
            return None
        existing_no = self._ids.get(key)
        if existing_no is None:
            return None
        existing = self._bookings.get_by_no(existing_no)
        if existing is None:
            return None
        return existing

    def _ensure_available(
        self,
        room_type_id: int,
        dates: list[date],
        room_count: int,
    ) -> None:
        """锁内复核：缺行、停售、余量不足都拒。"""
        rows = self._inventories.lock_rows(room_type_id, dates)
        found = {row.stay_date for row in rows}
        for day in dates:
            if day not in found:
                raise NoAvailabilityError(
                    "该日期没有库存记录（日历未铺满）",
                    room_type_id=room_type_id,
                    stay_date=date_text(day),
                )
        for row in rows:
            if not row.is_on_sale:
                raise NoAvailabilityError(
                    "该日期已停售",
                    room_type_id=room_type_id,
                    stay_date=date_text(row.stay_date),
                )
            if row.remaining < room_count:
                raise NoAvailabilityError(
                    "余量不足",
                    room_type_id=room_type_id,
                    stay_date=date_text(row.stay_date),
                    requested=room_count,
                    remaining=row.remaining,
                )

    def _ensure_reschedule_room(
        self,
        booking: Booking,
        new_dates: list[date],
        own_dates: set[date],
    ) -> None:
        """改期可用性判定：新日期余量 + 本单在这天已占的量，必须够本单间数。"""
        rows = self._inventories.lock_rows(booking.room_type_id, new_dates)
        found = {row.stay_date for row in rows}
        for day in new_dates:
            if day not in found:
                raise NoAvailabilityError(
                    "新日期没有库存记录（日历未铺满）",
                    room_type_id=booking.room_type_id,
                    stay_date=date_text(day),
                )
        for row in rows:
            if not row.is_on_sale:
                raise NoAvailabilityError(
                    "新日期已停售",
                    room_type_id=booking.room_type_id,
                    stay_date=date_text(row.stay_date),
                )
            effective = row.remaining + (booking.room_count if row.stay_date in own_dates else 0)
            if effective < booking.room_count:
                raise NoAvailabilityError(
                    "新日期余量不足",
                    room_type_id=booking.room_type_id,
                    stay_date=date_text(row.stay_date),
                    requested=booking.room_count,
                    remaining=effective,
                )

    def _release(self, booking: Booking) -> None:
        """把本单占用的房量逐日放回（同事务内，失败随事务回滚）。"""
        for day in booking.stay_dates:
            self._inventories.add_occupied(booking.room_type_id, day, -booking.room_count)

    def _visible(self, booking_no: str, actor: Actor) -> Booking:
        """取"看得见"的订单：不存在与无权访问返回同一 403 文案（S3-5）。"""
        booking = self._bookings.get_by_no(booking_no)
        if booking is None or not self._can_see(booking, actor):
            raise masked_booking_error()
        return booking

    @staticmethod
    def _can_see(booking: Booking, actor: Actor) -> bool:
        """可见性：管理员/系统看全部；顾客看自己；员工看本酒店。"""
        if actor.is_admin or actor.is_system:
            return True
        if actor.role is ActorRole.CUSTOMER:
            return booking.guest_id == actor.account_id
        return booking.hotel_id == actor.hotel_id

    @staticmethod
    def _assert_can_book(actor: Actor, guest_id: int) -> None:
        """下单权限：顾客只能给自己下单；管理员与系统不受限。"""
        if actor.is_admin or actor.is_system:
            return
        if actor.role is not ActorRole.CUSTOMER or actor.account_id != guest_id:
            raise PermissionDeniedError(
                "只能为本人下单",
                actor_id=actor.account_id,
                guest_id=guest_id,
            )

    @staticmethod
    def _new_booking_no(moment: datetime) -> str:
        """生成订单号：``BK`` + 秒级时间 + 4 位随机十六进制（唯一索引兜底）。"""
        return f"BK{moment.strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def _write_audit(
        self,
        booking: Booking,
        action: str,
        actor: Actor,
        before: BookingStatus | str | None,
        after: BookingStatus | str | None,
        reason: str | None = None,
    ) -> AuditLog:
        """追加一条订单审计（只追加，不修改）。

        六个参数是"谁、对哪张单、做了什么、从什么状态到什么状态、为什么"，
        每一列都对应 ``audit_log`` 的一列，合并成对象反而看不出缺了哪列。
        """
        log = AuditLog(
            operator_id=actor.account_id,
            operator_role=AUDIT_ROLE_CODE[actor.role],
            target_type="BOOKING",
            target_id=booking.booking_no,
            action=action,
            before_state=before.value if isinstance(before, BookingStatus) else before,
            after_state=after.value if isinstance(after, BookingStatus) else after,
            created_at=self._clock.now(),
            reason=reason,
        )
        return self._audits.append(log)
