"""领域异常：每个异常自带**机器可断言的错误码**与 HTTP 语义。

为什么不用裸 ``ValueError``：报告 R5 要给出"非法转换返回 409 且写审计"的证据，
测试与界面都要按错误码分支处理；把错误码钉在类型上，断言就变成
``assertEqual(error.code, "ILLEGAL_TRANSITION")``，不必匹配中文消息。
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """所有业务规则违反的基类。

    Attributes:
        code: 大写下划线错误码，供测试与界面分支使用。
        http_status: 对应 HTTP 语义（本项目是桌面应用，用于报告与日志对齐）。
        details: 结构化补充信息，例如 ``{"from": "PENDING", "event": "CHECK_OUT"}``。
    """

    code: str = "DOMAIN_ERROR"
    http_status: int = 400

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details

    def to_dict(self) -> dict[str, Any]:
        """序列化成可写日志/可回前端的结构。"""
        return {"code": self.code, "message": self.message, "details": self.details}

    def __str__(self) -> str:
        if not self.details:
            return self.message
        parts = ", ".join(f"{key}={value}" for key, value in self.details.items())
        return f"{self.message}（{parts}）"


class ValidationError(DomainError):
    """入参不合法（缺字段、日期顺序颠倒、间数 ≤ 0 等）。"""

    code = "VALIDATION_ERROR"
    http_status = 422


class IllegalTransitionError(DomainError):
    """非法状态转换：exp1 项目参数 §5 明令返回 409，且状态不变、写审计。"""

    code = "ILLEGAL_TRANSITION"
    http_status = 409


class PermissionDeniedError(DomainError):
    """角色无权执行该事件（例如顾客想替酒店确认订单）。"""

    code = "PERMISSION_DENIED"
    http_status = 403


class NoAvailabilityError(DomainError):
    """余量不足或当日停售，拒绝下单/改期。"""

    code = "NO_AVAILABILITY"
    http_status = 409


class DuplicateBookingError(DomainError):
    """同一顾客 + 同一酒店 + 同一房型 + 同时段已有有效订单（U6）。"""

    code = "DUPLICATE_BOOKING"
    http_status = 409


class InvalidStateError(DomainError):
    """数据自身不自洽（例如可售为负、占用超过可售）。"""

    code = "INVALID_STATE"
    http_status = 500
