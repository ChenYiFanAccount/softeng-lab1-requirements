"""领域服务：只编排**领域规则**，不碰事务、不碰幂等、不碰界面。

分层边界（与 ``exp2/设计基线/02_模块划分与交互.md`` 一致）：

* ``BookingStateMachine``：只管"哪条边能走、谁有权走"；
* ``InventoryService``：只管"这段日期还剩几间、能不能占"；
* ``BookingService``：把"校验 → 报价 → 建单 → 状态流转 → 写审计"串起来；
* 应用层（S3）：负责事务边界、幂等键、订单号生成、通知重试——**不在本模块**。

本模块只依赖仓储**接口**（``app.domain.repositories``），因此单测可以用内存假实现
直接跑，不需要 SQLite。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime

from app.domain.enums import ActorRole, BookingEvent, BookingStatus
from app.domain.errors import ValidationError
from app.domain.inventory import OccupancyPlan, assert_can_occupy, plan_occupancy
from app.domain.models import AuditLog, Booking, RoomType
from app.domain.pricing import Quote, quote, stay_dates
from app.domain.repositories import (
    AuditLogRepository,
    BookingRepository,
    InventoryRepository,
)
from app.domain.state_machine import BookingStateMachine, Transition


class InventoryService:
    """库存服务（对应类图 ``InventoryService``）。

    三条纪律：读与写走**同一入口**（``lock_rows``），避免"读到 3 间、写时只剩 1 间"；
    缺行/停售一律按 0 处理；任何判定都先校验间数（0 间是参数错误，不是没房）。
    """

    def __init__(
        self,
        inventories: InventoryRepository,
        room_types: Callable[[int], RoomType | None] | None = None,
    ) -> None:
        """注入库存仓储；``room_types`` 可选，用于校验"可售 ≤ 总房量"。"""
        self._inventories = inventories
        self._room_types = room_types

    @property
    def repository(self) -> InventoryRepository:
        """暴露仓储，供应用层在同一事务里复用。"""
        return self._inventories

    def remaining(self, room_type_id: int, dates: Sequence[date]) -> int:
        """区间余量上限（各日最小值；空区间为 0）。"""
        if not dates:
            return 0
        values = self._inventories.range_remaining(room_type_id, list(dates))
        return min(values) if values else 0

    def ensure_available(
        self, room_type_id: int, room_count: int, dates: Sequence[date]
    ) -> None:
        """校验区间可订；不可订时抛 409/422（细节见 :func:`assert_can_occupy`）。"""
        rows = self._inventories.lock_rows(room_type_id, list(dates))
        assert_can_occupy(rows, room_count)

    def plan(
        self, room_type_id: int, room_count: int, dates: Sequence[date]
    ) -> OccupancyPlan:
        """校验并生成占用计划（供事务内逐行 ``add_occupied``）。"""
        rows = self._inventories.lock_rows(room_type_id, list(dates))
        return plan_occupancy(rows, room_count)

    def ensure_can_adjust(self, room_type_id: int, new_available: int) -> None:
        """调整挂牌量前校验：新可售不得低于当日已占用，也不得超过总房量。"""
        if new_available < 0:
            raise ValidationError("可售间数不能为负", new_available=new_available)
        if self._room_types is None:
            return
        room_type = self._room_types(room_type_id)
        if room_type is None:
            raise ValidationError("房型不存在", room_type_id=room_type_id)
        if new_available > room_type.total_rooms:
            raise ValidationError(
                "可售间数不能超过总房量",
                new_available=new_available,
                total_rooms=room_type.total_rooms,
            )


class BookingService:
    """预订服务（对应类图 ``BookingService``）：领域侧的建单与状态流转。"""

    def __init__(
        self,
        bookings: BookingRepository,
        inventories: InventoryService,
        audits: AuditLogRepository | None = None,
        machine: BookingStateMachine | None = None,
    ) -> None:
        """注入三个协作对象；``audits`` 为空时只流转不记账（单测可省）。"""
        self._bookings = bookings
        self._inventories = inventories
        self._audits = audits
        self._machine = machine or BookingStateMachine()

    @property
    def machine(self) -> BookingStateMachine:
        """状态机实例（界面用它算"当前可做哪些操作"）。"""
        return self._machine

    def draft(  # pylint: disable=too-many-arguments
        self,
        *,
        booking_no: str,
        guest_id: int,
        hotel_id: int,
        room_type_id: int,
        check_in_date: date,
        check_out_date: date,
        room_count: int,
        nightly_prices: Mapping[date, int],
    ) -> Booking:
        """校验余量并生成**待确认**订单草稿（含逐晚快照），此时尚未落库。

        参数多（8 个）是业务决定的：谁下单、哪家酒店、哪个房型、哪天到哪天、几间、
        什么价，六要素缺一不可，且都不该有"悄悄生效"的默认值。

        Args:
            booking_no: 订单号，由应用层生成（领域层不关心编号规则）。
            guest_id: 下单顾客。
            hotel_id: 酒店。
            room_type_id: 房型。
            check_in_date: 入住日。
            check_out_date: 退房日。
            room_count: 间数。
            nightly_prices: ``{日期: 单价(分)}``，必须覆盖每一晚。

        Returns:
            状态为 ``PENDING`` 的订单对象，``nights`` 已按报价填好。

        Raises:
            ValidationError: 间数/日期/价格不合法（422）。
            NoAvailabilityError: 某晚余量不足或停售（409）。
        """
        quotation = quote(nightly_prices, check_in_date, check_out_date, room_count)
        self._inventories.ensure_available(
            room_type_id, room_count, self._dates(check_in_date, check_out_date)
        )
        return Booking(
            booking_no=booking_no,
            guest_id=guest_id,
            hotel_id=hotel_id,
            room_type_id=room_type_id,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            room_count=room_count,
            total_price_cents=quotation.total_cents,
            status=BookingStatus.PENDING,
            nights=quotation.to_booking_nights(0),
        )

    def quote_for(
        self,
        room_type_id: int,
        nightly_prices: Mapping[date, int],
        check_in_date: date,
        check_out_date: date,
        room_count: int,
    ) -> Quote:
        """只报价不校验余量（列表页展示用），返回逐晚明细。"""
        self._inventories.plan(
            room_type_id, room_count, self._dates(check_in_date, check_out_date)
        )
        return quote(nightly_prices, check_in_date, check_out_date, room_count)

    def apply_event(  # pylint: disable=too-many-arguments
        self,
        booking: Booking,
        event: BookingEvent,
        *,
        role: ActorRole,
        operator_id: int,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> Transition:
        """执行一次状态流转：改状态 → 保存订单 → 追加审计。

        Args:
            booking: 被操作的订单（就地修改）。
            event: 触发事件。
            role: 发起者角色（决定权限）。
            operator_id: 发起者账号 ID（写审计用）。
            reason: 取消原因等自由文本。
            at: 操作时间，缺省为当前时间。

        Returns:
            实际走通的 :class:`Transition`（编号 T1–T8 可直接进报告）。

        Raises:
            IllegalTransitionError: 非法转换（409，状态不变）。
            PermissionDeniedError: 角色无权（403）。
        """
        before = booking.status
        edge = self._machine.transition(booking, event, role=role, at=at, reason=reason)
        self._bookings.save(booking)
        if self._audits is not None:
            self._audits.append(
                AuditLog(
                    operator_id=operator_id,
                    operator_role=role.value,
                    target_type="BOOKING",
                    target_id=booking.booking_no,
                    action=edge.code,
                    before_state=before.value,
                    after_state=edge.target.value,
                    reason=reason,
                    created_at=at,
                )
            )
        return edge

    @staticmethod
    def _dates(check_in_date: date, check_out_date: date) -> list[date]:
        """入住期间每晚的日期（复用语域内的右开区间口径）。"""
        return stay_dates(check_in_date, check_out_date)
