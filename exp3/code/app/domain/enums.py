"""领域层枚举：状态、事件、操作者角色。

全部落库为**大写英文码**（与 ``0001_init.sql`` 的 CHECK 取值逐字一致），
中文只出现在界面层与报告里；这样 SQL 断言、日志检索、测试期望值三者可以共用
一个字符串，不需要在每处做翻译。
"""

from __future__ import annotations

from enum import StrEnum


class BookingStatus(StrEnum):
    """订单六状态（exp1 项目参数 §5：6 状态 / 8 条转换 / 5 条禁止）。"""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"

    @property
    def label(self) -> str:
        """中文名（界面与报告用，禁止写进 SQL）。"""
        return _STATUS_LABELS[self]

    @property
    def occupies_inventory(self) -> bool:
        """是否仍占用库存：待确认 / 已确认 / 已入住三种为"有效订单"。"""
        return self in ACTIVE_STATUSES

    @property
    def is_terminal(self) -> bool:
        """是否终态：已退房 / 已取消 / 未入住，进入后不再改变。"""
        return self in TERMINAL_STATUSES


class BookingEvent(StrEnum):
    """驱动状态转换的八个事件（与 8 条转换边一一对应）。"""

    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    TIMEOUT = "TIMEOUT"
    CHECK_IN = "CHECK_IN"
    AUTO_CHECK_IN = "AUTO_CHECK_IN"
    CANCEL = "CANCEL"
    NO_SHOW = "NO_SHOW"
    CHECK_OUT = "CHECK_OUT"

    @property
    def label(self) -> str:
        """中文名，用于审计日志与 409 提示。"""
        return _EVENT_LABELS[self]


class ActorRole(StrEnum):
    """四类操作者。``SYSTEM`` 不是登录身份，只用于调度任务写入审计。"""

    CUSTOMER = "CUSTOMER"
    HOTEL_STAFF = "HOTEL_STAFF"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    SYSTEM = "SYSTEM"

    @property
    def label(self) -> str:
        """中文名，用于界面与报告。"""
        return _ROLE_LABELS[self]


class AccountStatus(StrEnum):
    """账号状态（``user_account.status``）：只有 ``ACTIVE`` 能登录。"""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"

    @property
    def label(self) -> str:
        """中文名，用于界面与报告。"""
        return _ACCOUNT_STATUS_LABELS[self]


class HolidayStatus(StrEnum):
    """节假日条目状态（``holiday_calendar.status``）：停用后不参与调价与取消政策。"""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"

    @property
    def label(self) -> str:
        """中文名，用于界面与报告。"""
        return _HOLIDAY_STATUS_LABELS[self]


class HotelAuditStatus(StrEnum):
    """酒店审核状态（``hotel.audit_status``）：只有通过审核的酒店才能售卖。"""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

    @property
    def label(self) -> str:
        """中文名，用于界面与报告。"""
        return _AUDIT_STATUS_LABELS[self]


#: 允许登录的账号状态集合（用集合成员判断，避免把魔法字符串散进领域模型）
ENABLED_ACCOUNT_STATUSES: frozenset[AccountStatus] = frozenset({AccountStatus.ACTIVE})

#: 参与价格与取消策略计算的节假日状态集合
ENABLED_HOLIDAY_STATUSES: frozenset[HolidayStatus] = frozenset({HolidayStatus.ENABLED})

#: 允许对外售卖的酒店审核状态集合
SELLABLE_AUDIT_STATUSES: frozenset[HotelAuditStatus] = frozenset({HotelAuditStatus.APPROVED})

ACTIVE_STATUSES: frozenset[BookingStatus] = frozenset(
    {BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN}
)
TERMINAL_STATUSES: frozenset[BookingStatus] = frozenset(
    {BookingStatus.CHECKED_OUT, BookingStatus.CANCELLED, BookingStatus.NO_SHOW}
)

#: 系统服务账号的固定主键：调度器（超时取消/自动入住/no-show）以它为操作者落库，
#: 因为 ``stay_record.operator_id`` 是指向 ``user_account`` 的 NOT NULL 外键。
SYSTEM_ACCOUNT_ID = 0

_STATUS_LABELS: dict[BookingStatus, str] = {
    BookingStatus.PENDING: "待确认",
    BookingStatus.CONFIRMED: "已确认",
    BookingStatus.CHECKED_IN: "已入住",
    BookingStatus.CHECKED_OUT: "已退房",
    BookingStatus.CANCELLED: "已取消",
    BookingStatus.NO_SHOW: "未入住",
}

_EVENT_LABELS: dict[BookingEvent, str] = {
    BookingEvent.CONFIRM: "酒店确认",
    BookingEvent.REJECT: "酒店拒单",
    BookingEvent.TIMEOUT: "超时未确认（系统）",
    BookingEvent.CHECK_IN: "办理入住",
    BookingEvent.AUTO_CHECK_IN: "系统次日默认置为已入住",
    BookingEvent.CANCEL: "取消订单",
    BookingEvent.NO_SHOW: "标记未入住",
    BookingEvent.CHECK_OUT: "办理退房",
}

_ROLE_LABELS: dict[ActorRole, str] = {
    ActorRole.CUSTOMER: "顾客",
    ActorRole.HOTEL_STAFF: "酒店工作人员",
    ActorRole.PLATFORM_ADMIN: "平台管理员",
    ActorRole.SYSTEM: "系统",
}

_ACCOUNT_STATUS_LABELS: dict[AccountStatus, str] = {
    AccountStatus.ACTIVE: "正常",
    AccountStatus.DISABLED: "停用",
}

_HOLIDAY_STATUS_LABELS: dict[HolidayStatus, str] = {
    HolidayStatus.ENABLED: "启用",
    HolidayStatus.DISABLED: "停用",
}

_AUDIT_STATUS_LABELS: dict[HotelAuditStatus, str] = {
    HotelAuditStatus.PENDING: "待审核",
    HotelAuditStatus.APPROVED: "已通过",
    HotelAuditStatus.REJECTED: "已驳回",
}
