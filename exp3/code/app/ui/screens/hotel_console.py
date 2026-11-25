"""屏 5：酒店订单台（确认 / 拒单 / 办理入住 / 退房 / 标记未入住）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.domain.enums import BookingEvent
from app.domain.errors import DomainError
from app.ui.format import day_text, money, status_text
from app.ui.screens.base import BaseScreen

#: 动作按钮 → 事件；顺序按营业流程排，不按枚举定义顺序
ACTIONS: tuple[tuple[str, BookingEvent], ...] = (
    ("确认预订", BookingEvent.CONFIRM),
    ("拒单", BookingEvent.REJECT),
    ("办理入住", BookingEvent.CHECK_IN),
    ("办理退房", BookingEvent.CHECK_OUT),
    ("标记未入住", BookingEvent.NO_SHOW),
)


class HotelConsoleScreen(BaseScreen):
    """酒店员工视角：本店订单列表 + 五个状态机动作。"""

    TITLE = "酒店订单台"
    SUBTITLE = "只有本店员工能操作本店订单；每次动作都写审计，失败也会留痕。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        toolbar = ttk.Frame(self, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(12, 0))
        ttk.Label(toolbar, text="筛选", style="Body.TLabel").pack(side="left")
        self.filter = tk.StringVar(value="全部")
        box = ttk.Combobox(
            toolbar, textvariable=self.filter, width=10, state="readonly",
            values=("全部", "待确认", "已确认", "已入住", "已退房", "已取消", "未入住"),
        )
        box.pack(side="left", padx=8)
        box.bind("<<ComboboxSelected>>", lambda event: self.reload())
        ttk.Button(toolbar, text="刷新", style="Ghost.TButton", command=self.reload).pack(side="left")

        # 动作按钮必须排在会 expand 的表格之前：pack 先分配固定尺寸的兄弟，
        # 排在 expand 之后的控件会被挤成 0 高（本屏实测按钮整排消失）。
        actions = ttk.Frame(self, style="Card.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        for label, event in ACTIONS:
            style = "Primary.TButton" if event is BookingEvent.CONFIRM else "Ghost.TButton"
            ttk.Button(
                actions, text=label, style=style,
                command=lambda chosen=event: self.apply(chosen),
            ).pack(side="left", padx=(0, 8))
        self.reason = tk.StringVar()
        self.entry_row(actions, "原因", var=self.reason, width=18).pack(side="left", padx=(12, 0))

        self.message_label = self.message(self)
        self.summary = ttk.Label(self, text="", style="Muted.TLabel")
        self.summary.pack(anchor="w")

        self.tree = self.table(
            self,
            columns=[
                ("no", "订单号", 170),
                ("guest", "顾客", 80),
                ("stay", "入住区间", 160),
                ("rooms", "间", 40),
                ("total", "合计", 80),
                ("status", "状态", 70),
            ],
            height=10,
        )

    def on_show(self) -> None:
        self.reload()

    def hotel_id(self) -> int | None:
        """当前员工所属酒店；管理员返回 None（表示全平台）。"""
        actor = self.session.actor
        if actor is None:
            return None
        return None if actor.is_admin else actor.hotel_id

    def reload(self) -> None:
        """取本店订单并按下拉框过滤。"""
        actor = self.session.actor
        if actor is None:
            self.fill(self.tree, [])
            self.set_message(self.message_label, "请先登录", ok=False)
            return
        try:
            bookings = self.session.bookings().list_hotel_bookings(
                actor, self.hotel_id(), limit=200
            )
        except DomainError as error:
            self.set_message(self.message_label, f"读取失败：{error}", ok=False)
            return
        wanted = self.filter.get()
        shown = [
            booking
            for booking in bookings
            if wanted == "全部" or status_text(booking.status.value) == wanted
        ]
        self.fill(
            self.tree,
            [
                (
                    booking.booking_no,
                    f"#{booking.guest_id}",
                    f"{day_text(booking.check_in_date)} → {day_text(booking.check_out_date)}",
                    booking.room_count,
                    money(booking.total_price_cents),
                    status_text(booking.status.value),
                )
                for booking in shown
            ],
            raw=shown,
        )
        counts: dict[str, int] = {}
        for booking in bookings:
            label = status_text(booking.status.value)
            counts[label] = counts.get(label, 0) + 1
        detail = "，".join(f"{key} {value}" for key, value in sorted(counts.items())) or "无订单"
        self.summary.configure(text=f"本店共 {len(bookings)} 笔：{detail}")
        self.set_message(self.message_label, f"当前显示 {len(shown)} 笔", ok=True)

    def apply(self, event: BookingEvent) -> None:
        """把按钮点击转成一次状态机动作；异常文案直接显示。"""
        booking = self.selected_raw(self.tree)
        if booking is None:
            self.set_message(self.message_label, "请先选中一笔订单", ok=False)
            return
        actor = self.session.actor
        if actor is None:
            self.set_message(self.message_label, "请先登录", ok=False)
            return
        try:
            updated = self.session.bookings().apply_event(
                booking.booking_no, event, actor, reason=(self.reason.get().strip() or None)
            )
        except DomainError as error:
            self.set_message(self.message_label, f"{event.label}失败：{error}", ok=False)
            return
        self.set_message(
            self.message_label,
            f"{booking.booking_no} 已{event.label} → {status_text(updated.status.value)}",
            ok=True,
        )
        self.window.set_status(f"{event.label} {booking.booking_no}")
        self.reload()
