"""展示格式：分转元、千分比转百分比、状态码转中文。

界面不许自己做金额运算（S6 约束 2：不要在界面里二次加工金额/比率），
所以这里只做**字符串化**，不做任何算术——除了 `//` 与 `%` 这种"拆整数部分"。
"""

from __future__ import annotations

from datetime import date, datetime

from app.domain.enums import (
    AccountStatus,
    ActorRole,
    BookingEvent,
    BookingStatus,
    HolidayStatus,
    HotelAuditStatus,
)

MONEY_SYMBOL = "¥"
PLACEHOLDER = "—"


def money(cents: int | None) -> str:
    """整数分转"¥123.45"；``None`` 表示尚未配价。"""
    if cents is None:
        return PLACEHOLDER
    sign = "-" if cents < 0 else ""
    value = abs(int(cents))
    return f"{sign}{MONEY_SYMBOL}{value // 100}.{value % 100:02d}"


def permille(value: int) -> str:
    """千分比转百分比显示（整数一位小数，不引入浮点）。"""
    sign = "-" if value < 0 else ""
    size = abs(int(value))
    return f"{sign}{size // 10}.{size % 10}%"


def day_text(day: date | datetime | None) -> str:
    """日期显示；``datetime`` 只取日期部分。"""
    if day is None:
        return PLACEHOLDER
    if isinstance(day, datetime):
        return day.strftime("%Y-%m-%d")
    return day.isoformat()


def moment_text(moment: datetime | None) -> str:
    """时刻显示（本地时区由系统决定，库里存的是 UTC）。"""
    if moment is None:
        return PLACEHOLDER
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def status_text(code: str) -> str:
    """订单状态中文名；未知码原样返回，便于发现脏数据。"""
    try:
        return BookingStatus(code).label
    except ValueError:
        return code


def event_text(code: str) -> str:
    """订单事件中文名；审计里的 ``CREATE`` / ``RESCHEDULE`` 等直接原样。"""
    try:
        return BookingEvent(code).label
    except ValueError:
        return code


def role_text(code: str) -> str:
    """角色中文名。"""
    try:
        return ActorRole(code).label
    except ValueError:
        return code


def audit_status_text(code: str) -> str:
    """酒店审核状态中文名。"""
    try:
        return HotelAuditStatus(code).label
    except ValueError:
        return code


def account_status_text(code: str) -> str:
    """账号状态中文名。"""
    try:
        return AccountStatus(code).label
    except ValueError:
        return code


def holiday_status_text(code: str) -> str:
    """节假日开关中文名。"""
    try:
        return HolidayStatus(code).label
    except ValueError:
        return code
