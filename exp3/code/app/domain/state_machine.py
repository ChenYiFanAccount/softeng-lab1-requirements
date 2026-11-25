"""订单状态机：**表驱动**的 8 条允许边 + 5 条显式禁止边。

为什么必须表驱动（S2-3 判据）：状态判断一旦散写成"当前状态是待确认就……"的链式
分支，新增一条边就要改多处，且"哪些转换是非法"的没有单一出处，报告也无法给出可数
的证据。这里：

* ``TRANSITIONS`` 是允许边的**唯一真源**（8 条，含同状态对的两种触发者）；
* ``FORBIDDEN_TRANSITIONS`` 把 5 条"画成允许就是错"的边连同理由钉住，用于 409 提示；
* 任何状态改动都必须经过 :meth:`BookingStateMachine.transition`，
  它只认 ``(当前状态, 事件)`` 这一把钥匙。

状态卡（exp1 项目参数 §5）：

=================  ==========  ==========================  ==================
编号               事件        来源 → 目标                 允许角色
=================  ==========  ==========================  ==================
T1                 CONFIRM     待确认 → 已确认              酒店 / 管理员
T2                 REJECT      待确认 → 已取消              酒店 / 管理员
T3                 TIMEOUT     待确认 → 已取消              系统
T4                 CHECK_IN    已确认 → 已入住              酒店
T5                 AUTO_CHECK_IN 已确认 → 已入住            系统
T6                 CANCEL      已确认 → 已取消              顾客 / 酒店 / 管理员
T7                 NO_SHOW     已确认 → 未入住              酒店 / 系统
T8                 CHECK_OUT   已入住 → 已退房              酒店
=================  ==========  ==========================  ==================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import ActorRole, BookingEvent, BookingStatus
from app.domain.errors import IllegalTransitionError, PermissionDeniedError
from app.domain.models import Booking


@dataclass(frozen=True, slots=True)
class Transition:
    """一条允许的状态转换边。"""

    code: str
    event: BookingEvent
    source: BookingStatus
    target: BookingStatus
    allowed_roles: frozenset[ActorRole]
    trigger: str

    def describe(self) -> str:
        """``T6 取消订单：已确认 → 已取消`` 形式的单行描述（审计与报告共用）。"""
        return (
            f"{self.code} {self.event.label}："
            f"{self.source.label} → {self.target.label}"
        )


TRANSITIONS: tuple[Transition, ...] = (
    Transition(
        code="T1",
        event=BookingEvent.CONFIRM,
        source=BookingStatus.PENDING,
        target=BookingStatus.CONFIRMED,
        allowed_roles=frozenset({ActorRole.HOTEL_STAFF, ActorRole.PLATFORM_ADMIN}),
        trigger="酒店工作人员确认预订",
    ),
    Transition(
        code="T2",
        event=BookingEvent.REJECT,
        source=BookingStatus.PENDING,
        target=BookingStatus.CANCELLED,
        allowed_roles=frozenset({ActorRole.HOTEL_STAFF, ActorRole.PLATFORM_ADMIN}),
        trigger="酒店拒单",
    ),
    Transition(
        code="T3",
        event=BookingEvent.TIMEOUT,
        source=BookingStatus.PENDING,
        target=BookingStatus.CANCELLED,
        allowed_roles=frozenset({ActorRole.SYSTEM}),
        trigger="30 分钟超时未确认，系统自动取消并回补库存",
    ),
    Transition(
        code="T4",
        event=BookingEvent.CHECK_IN,
        source=BookingStatus.CONFIRMED,
        target=BookingStatus.CHECKED_IN,
        allowed_roles=frozenset({ActorRole.HOTEL_STAFF}),
        trigger="酒店凭订单号或手机号核验办理入住",
    ),
    Transition(
        code="T5",
        event=BookingEvent.AUTO_CHECK_IN,
        source=BookingStatus.CONFIRMED,
        target=BookingStatus.CHECKED_IN,
        allowed_roles=frozenset({ActorRole.SYSTEM}),
        trigger="入住日 23:59 前未标记且未到店，系统次日置为已入住",
    ),
    Transition(
        code="T6",
        event=BookingEvent.CANCEL,
        source=BookingStatus.CONFIRMED,
        target=BookingStatus.CANCELLED,
        allowed_roles=frozenset(
            {ActorRole.CUSTOMER, ActorRole.HOTEL_STAFF, ActorRole.PLATFORM_ADMIN}
        ),
        trigger="顾客按取消政策取消 / 酒店停业或超售取消 / 管理员强制取消",
    ),
    Transition(
        code="T7",
        event=BookingEvent.NO_SHOW,
        source=BookingStatus.CONFIRMED,
        target=BookingStatus.NO_SHOW,
        allowed_roles=frozenset({ActorRole.HOTEL_STAFF, ActorRole.SYSTEM}),
        trigger="酒店在入住日 23:59 前标记未入住",
    ),
    Transition(
        code="T8",
        event=BookingEvent.CHECK_OUT,
        source=BookingStatus.CHECKED_IN,
        target=BookingStatus.CHECKED_OUT,
        allowed_roles=frozenset({ActorRole.HOTEL_STAFF}),
        trigger="酒店办理退房，订单完结",
    ),
)

#: 5 条禁止边：键为 ``(来源状态, 事件)``，值为"为什么不行"。
FORBIDDEN_TRANSITIONS: dict[tuple[BookingStatus, BookingEvent], str] = {
    (BookingStatus.CHECKED_IN, BookingEvent.CANCEL): (
        "已实际入住，费用与库存已发生，不能取消（F1）"
    ),
    (BookingStatus.CHECKED_OUT, BookingEvent.CANCEL): "订单已完结，不能取消（F2）",
    (BookingStatus.CANCELLED, BookingEvent.CONFIRM): (
        "库存已回补，恢复确认会造成重复占用（F3）"
    ),
    (BookingStatus.CHECKED_IN, BookingEvent.CONFIRM): "状态回退到确认不允许（F4）",
    (BookingStatus.CHECKED_OUT, BookingEvent.CHECK_IN): "状态回退到入住不允许（F5）",
}

_INDEX: dict[tuple[BookingStatus, BookingEvent], Transition] = {
    (edge.source, edge.event): edge for edge in TRANSITIONS
}


class BookingStateMachine:
    """订单状态机：查询、校验、执行三件事，全部只读 ``TRANSITIONS``。"""

    def __init__(self) -> None:
        self._index: dict[tuple[BookingStatus, BookingEvent], Transition] = dict(_INDEX)

    @property
    def transitions(self) -> tuple[Transition, ...]:
        """允许边的只读视图（报告里"8 条边"的数字来源）。"""
        return TRANSITIONS

    def lookup(self, current: BookingStatus, event: BookingEvent) -> Transition | None:
        """按 ``(当前状态, 事件)`` 查允许边；没有则返回 ``None``。"""
        return self._index.get((current, event))

    def is_allowed(
        self,
        current: BookingStatus,
        event: BookingEvent,
        role: ActorRole | None = None,
    ) -> bool:
        """该状态下该事件是否被允许（可选校验角色）。"""
        edge = self.lookup(current, event)
        if edge is None:
            return False
        return role is None or role in edge.allowed_roles

    def available_events(
        self, current: BookingStatus, role: ActorRole | None = None
    ) -> tuple[BookingEvent, ...]:
        """当前状态下的可用事件列表（界面上"这个订单能点哪些按钮"由此生成）。"""
        return tuple(
            edge.event
            for edge in TRANSITIONS
            if edge.source == current and (role is None or role in edge.allowed_roles)
        )

    def is_terminal(self, status: BookingStatus) -> bool:
        """是否终态（终态没有任何出边，可由 ``TRANSITIONS`` 反证）。"""
        if status.is_terminal:
            return True
        return not any(edge.source == status for edge in TRANSITIONS)

    def assert_allowed(
        self,
        current: BookingStatus,
        event: BookingEvent,
        role: ActorRole | None = None,
    ) -> Transition:
        """校验并返回对应边，不合法则抛异常（供"只校验不改状态"的调用方使用）。

        Raises:
            IllegalTransitionError: 该状态没有这条边（409，状态不变）。
            PermissionDeniedError: 边存在但角色无权（403）。
        """
        edge = self.lookup(current, event)
        if edge is None:
            raise IllegalTransitionError(
                self.reject_reason(current, event, role),
                **self._conflict_details(current, event),
            )
        if role is not None and role not in edge.allowed_roles:
            raise PermissionDeniedError(
                f"{role.label}无权执行「{event.label}」",
                from_status=current.value,
                event=event.value,
                allowed_roles=sorted(item.value for item in edge.allowed_roles),
            )
        return edge

    def transition(
        self,
        booking: Booking,
        event: BookingEvent,
        *,
        role: ActorRole,
        at: datetime | None = None,
        reason: str | None = None,
    ) -> Transition:
        """执行一次状态转换（**唯一的**状态写入口）。

        Args:
            booking: 待转换的订单（其 ``status`` 为当前状态）。
            event: 触发事件。
            role: 操作者角色，用于权限校验与审计。
            at: 转换时间（默认不修改，时间戳由应用服务写入审计）。
            reason: 取消/拒绝原因，写入订单的 ``cancel_reason``。

        Returns:
            实际执行的 :class:`Transition`。

        Raises:
            IllegalTransitionError: 非法转换（409，订单状态保持不变）。
            PermissionDeniedError: 角色无权执行该事件（403）。
        """
        edge = self.assert_allowed(booking.status, event, role)
        booking.apply_status(edge.target)
        if reason is not None and edge.target is BookingStatus.CANCELLED:
            booking.cancel_reason = reason
            booking.cancel_initiator = role.value
        if at is not None:
            booking.updated_at = at
        return edge

    def reject_reason(
        self,
        current: BookingStatus,
        event: BookingEvent,
        role: ActorRole | None = None,
    ) -> str:
        """生成给人看的拒绝原因（409 消息正文）。

        顺序：先看是否是 5 条显式禁止边（理由更具体），再看角色权限，
        最后才落到"该状态不支持该事件"的通用说法。
        """
        forbidden = FORBIDDEN_TRANSITIONS.get((current, event))
        if forbidden is not None:
            return f"非法转换：{forbidden}"
        edge = self.lookup(current, event)
        if edge is not None and role is not None and role not in edge.allowed_roles:
            allowed = "、".join(sorted(item.label for item in edge.allowed_roles))
            return f"权限不足：{event.label}只允许 {allowed} 执行，当前为 {role.label}"
        target = current.label
        terminal = "（终态）" if self.is_terminal(current) else ""
        return f"非法转换：{target}{terminal}不接受事件「{event.label}」"

    @staticmethod
    def _conflict_details(
        current: BookingStatus, event: BookingEvent
    ) -> dict[str, str]:
        """409 响应里的结构化字段（测试按这两个键断言）。"""
        return {"from_status": current.value, "event": event.value}
