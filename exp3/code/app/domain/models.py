"""领域实体：13 个核心类型中的 12 个可落库实体（``BookingStatus`` 是枚举，见 enums）。

设计约束（与 ``exp2/UML/UML类图.puml`` 逐字对齐，类名即 UML 别名）：

* 字段用 **Python 原生类型**（``date``/``int``/``str``），金额一律 **整数分**；
* 所有派生量（余量、天数、小计、总价）都是**方法或属性**，不落库；
* 实体自身**不做 I/O**：不知道 SQLite、不知道仓储，方便单测直接构造；
* 状态字段只允许经 ``BookingStateMachine`` 修改——``Booking`` 提供
  ``apply_status`` 包一层，并在其中断言目标状态来自状态机给出的转移结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from app.domain.enums import BookingStatus
from app.domain.errors import InvalidStateError, ValidationError


@dataclass(slots=True)
class UserAccount:
    """用户账号（13 类之一，对应 ``user_account`` 表）。

    「角色」是枚举字段而不是独立实体：数据设计里没有角色表，类图也不单列 ``Role``。
    """

    account_id: int
    login_name: str
    password_hash: str
    role: str
    hotel_id: int | None = None
    status: str = "ACTIVE"
    created_at: datetime | None = None

    @property
    def is_enabled(self) -> bool:
        """账号是否可用（``DISABLED`` 不得登录）。"""
        return self.status == "ACTIVE"

    def verify_password(self, plaintext: str, verifier: Callable[[str, str], bool]) -> bool:
        """校验明文口令。

        哈希算法属于基础设施细节（``app.infrastructure.security``），领域层只声明
        "需要一个校验函数"，避免领域依赖具体加密实现。

        Args:
            plaintext: 用户输入的明文口令。
            verifier: ``(plaintext, password_hash) -> bool`` 的校验函数。

        Returns:
            口令是否正确。
        """
        return verifier(plaintext, self.password_hash)


@dataclass(slots=True)
class Hotel:  # pylint: disable=too-many-instance-attributes
    """酒店（对应 ``hotel`` 表），需平台审核通过才能售卖。

    字段是"表的列"的镜像，数量由数据设计决定，不是上帝类。
    """

    hotel_id: int
    name: str
    address: str
    phone: str
    description: str | None = None
    audit_status: str = "PENDING"
    reject_reason: str | None = None
    created_at: datetime | None = None
    audited_at: datetime | None = None

    @property
    def is_approved(self) -> bool:
        """是否审核通过（``REJECTED`` 必须带驳回原因，由 CHECK 保证）。"""
        return self.audit_status == "APPROVED"


@dataclass(slots=True)
class RoomType:
    """房型（对应 ``room_type`` 表）——总房量是**上限**，不是每日可售量。"""

    room_type_id: int
    hotel_id: int
    name: str
    bed_type: str
    area_sqm: int
    capacity: int
    total_rooms: int

    def occupied_exceeds_total(self, occupied_rooms: int) -> bool:
        """已占用是否超过总房量。

        注意：行内 CHECK 只能表达 ``占用 ≤ 可售``，``可售 ≤ 总房量`` 这条跨表规则
        必须由本方法在应用层把关（S1 交付说明 D3 已登记该实现口径）。
        """
        return occupied_rooms > self.total_rooms

    def assert_occupied_within_total(self, occupied_rooms: int) -> None:
        """占用超过总房量时抛 :class:`InvalidStateError`。"""
        if self.occupied_exceeds_total(occupied_rooms):
            raise InvalidStateError(
                "占用间数超过总房量",
                room_type_id=self.room_type_id,
                total_rooms=self.total_rooms,
                occupied_rooms=occupied_rooms,
            )


@dataclass(slots=True)
class RoomInventory:
    """每日库存（对应 ``room_inventory`` 表），主键为「房型 × 日期」。

    口径（全系统唯一一套，类图 note 原文）：

    * 可售间数 = 酒店按日挂牌的可售量（落库）；
    * 已占用间数 = 有效订单占用（落库）；
    * **余量 = 可售 − 占用，是方法，不落库**。
    """

    room_type_id: int
    stay_date: date
    available_rooms: int
    occupied_rooms: int = 0
    sale_status: str = "ON_SALE"
    updated_at: datetime | None = None

    @property
    def remaining(self) -> int:
        """余量（可售 − 占用）；正常数据下恒 ≥ 0。"""
        return self.available_rooms - self.occupied_rooms

    @property
    def is_on_sale(self) -> bool:
        """当日是否在售；停售日任何下单都必须按余量 0 处理。"""
        return self.sale_status == "ON_SALE"

    def can_occupy(self, room_count: int) -> bool:
        """在售且余量够，才算可占用。"""
        return self.is_on_sale and 0 < room_count <= self.remaining

    def can_adjust_available(self, new_available: int) -> bool:
        """调整可售量时不得低于已占用（否则余量为负）。"""
        return new_available >= self.occupied_rooms


@dataclass(slots=True)
class RoomPrice:
    """每日价格（对应 ``room_price`` 表），单价为整数分。"""

    room_type_id: int
    stay_date: date
    unit_price_cents: int

    def subtotal_cents(self, room_count: int) -> int:
        """``单价 × 间数``（整数分）。"""
        return self.unit_price_cents * room_count


@dataclass(slots=True)
class BookingNight:
    """逐晚快照（对应 ``booking_night`` 表）。

    为什么单独一个类型：房型价格按「房型 × 日期」维护，一单跨多晚、每晚价格可能
    不同，总价 = Σ(单价快照 × 间数)，单一"单价快照"字段表达不了。
    """

    booking_id: int
    stay_date: date
    unit_price_cents: int
    room_count: int

    def subtotal_cents(self) -> int:
        """本晚小计 = 单价快照 × 间数。"""
        return self.unit_price_cents * self.room_count


@dataclass(slots=True)
class Booking:  # pylint: disable=too-many-instance-attributes
    """订单（对应 ``booking`` 表）——唯一允许改动状态的实体。

    字段多是因为它同时承载"订单头 + 取消信息 + 逐晚快照"三组信息；
    拆成三个类反而会让一次事务要写三处，违背"一单一事务"的口径。
    """

    booking_no: str
    guest_id: int
    hotel_id: int
    room_type_id: int
    check_in_date: date
    check_out_date: date
    room_count: int
    total_price_cents: int
    status: BookingStatus
    booking_id: int | None = None
    idempotency_key: str | None = None
    cancel_reason: str | None = None
    cancel_initiator: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    nights: list[BookingNight] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.room_count <= 0:
            raise ValidationError("间数必须大于 0", room_count=self.room_count)
        if self.check_out_date <= self.check_in_date:
            raise ValidationError(
                "退房日必须晚于入住日",
                check_in=str(self.check_in_date),
                check_out=str(self.check_out_date),
            )
        if self.total_price_cents < 0:
            raise ValidationError("总价不能为负", total_price_cents=self.total_price_cents)

    @property
    def stay_dates(self) -> list[date]:
        """入住期间每一晚的日期（退房日当天不住，故右开区间）。"""
        return [
            self.check_in_date + timedelta(days=offset)
            for offset in range(self.nights_count)
        ]

    @property
    def nights_count(self) -> int:
        """占用天数 = 退房日 − 入住日。"""
        return (self.check_out_date - self.check_in_date).days

    @property
    def is_active(self) -> bool:
        """是否有效订单（待确认 / 已确认 / 已入住）——库存与 U6 都按此口径。"""
        return self.status.occupies_inventory

    @property
    def is_terminal(self) -> bool:
        """是否已完结（已退房 / 已取消 / 未入住）。"""
        return self.status.is_terminal

    def recompute_total_price(self) -> int:
        """按逐晚快照重算总价（整数分），用于对账与校验快照一致性。"""
        return sum(night.subtotal_cents() for night in self.nights)

    def apply_status(self, target: BookingStatus) -> None:
        """由状态机调用的**唯一**状态写入口。

        这里不做合法性判断（状态机已经判过），只拒绝"写入一个非法的状态值"，
        即兜底防止别处直接赋一个未定义的字符串。

        Args:
            target: 状态机给出的目标状态。

        Raises:
            InvalidStateError: 目标不是 :class:`BookingStatus` 的成员。
        """
        if not isinstance(target, BookingStatus):
            raise InvalidStateError("目标状态必须是 BookingStatus 成员", target=str(target))
        self.status = target


@dataclass(slots=True)
class IdempotencyKey:
    """幂等键（对应 ``idempotency_key`` 表）：同一键重复提交必须返回同一张订单。"""

    key_value: str
    created_at: datetime | None = None
    booking_no: str | None = None


@dataclass(slots=True)
class StayRecord:
    """办理记录（对应 ``stay_record`` 表）：入住 / 退房 / 未入住的流水。"""

    booking_id: int
    action: str
    operator_id: int
    source: str
    created_at: datetime | None = None
    remark: str | None = None
    record_id: int | None = None


@dataclass(slots=True)
class AuditLog:  # pylint: disable=too-many-instance-attributes
    """审计日志（对应 ``audit_log`` 表）：只追加、不建外键（弱引用保历史）。"""

    operator_id: int
    operator_role: str
    target_type: str
    target_id: str
    action: str
    created_at: datetime | None = None
    before_state: str | None = None
    after_state: str | None = None
    reason: str | None = None
    log_id: int | None = None

    def describe(self) -> str:
        """单行摘要，供界面"操作审计"列表直接显示。"""
        before = self.before_state or "-"
        after = self.after_state or "-"
        return f"{self.action}: {before} → {after}"


@dataclass(slots=True)
class NotificationRecord:
    """通知记录（对应 ``notification_record`` 表）：D-017 取 UML ∪ 数据设计并集。"""

    booking_id: int
    channel: str
    content_summary: str
    result: str = "PENDING_NEGOTIATION"
    notified_at: datetime | None = None
    record_id: int | None = None


@dataclass(slots=True)
class HolidayCalendar:
    """平台级节假日字典（对应 ``holiday_calendar`` 表），供取消政策与调价引用。"""

    holiday_date: date
    name: str | None = None
    status: str = "ENABLED"

    @property
    def is_enabled(self) -> bool:
        """是否启用；停用后不再参与价格与取消策略计算。"""
        return self.status == "ENABLED"
