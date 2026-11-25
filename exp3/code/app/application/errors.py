"""应用层错误与"不泄露存在性"的统一文案。

S3-5 要求：越权访问返回 403，且**对不存在的订单与无权访问的订单返回同一
错误码与同一文案**。做法是两种情况都走 :data:`MASKED_BOOKING_MESSAGE`，
调用方无法通过错误信息判断订单是否真实存在。

另外补一个应用层专用的 :class:`ConflictError`（HTTP 409）：领域层的
``IllegalTransitionError`` 表达"状态机不允许"，而"只有已确认订单可以改期"
这类**流程前置条件**不属于状态机，用本类的 ``code = "CONFLICT"`` 区分。
"""

from __future__ import annotations

from app.domain.errors import DomainError, PermissionDeniedError, ValidationError

#: 不存在 / 无权访问 共用的文案（刻意不区分）
MASKED_BOOKING_MESSAGE = "无权访问该订单或订单不存在"


class ConflictError(DomainError):
    """当前状态满足不了流程前置条件（如改期只允许已确认订单）。"""

    code = "CONFLICT"
    http_status = 409


def masked_booking_error() -> PermissionDeniedError:
    """构造"看不见的订单"错误：403 + 统一文案。"""
    return PermissionDeniedError(MASKED_BOOKING_MESSAGE)


def bad_request(message: str, **details: object) -> ValidationError:
    """参数错误快捷构造，HTTP 422。"""
    return ValidationError(message, **details)
