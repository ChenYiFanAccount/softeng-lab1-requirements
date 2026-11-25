"""屏 4：我的订单 + 订单详情（顶部工具栏放详情与动作，取消 / 改期在此发起）。"""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.application.commands import RescheduleCommand
from app.domain.enums import BookingEvent
from app.domain.errors import DomainError
from app.ui.format import day_text, money, status_text
from app.ui.screens.base import BaseScreen


class MyOrdersScreen(BaseScreen):
    """顾客视角的订单列表；选中后右侧展示详情与可用动作。"""

    TITLE = "我的订单"
    SUBTITLE = "选中一笔订单查看详情；取消、改期等动作走状态机，非法转换会被拒绝并写审计。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        toolbar = ttk.Frame(self, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(12, 0))
        self.reason = tk.StringVar()
        self.entry_row(toolbar, "原因", var=self.reason, width=18).pack(side="left", padx=(0, 12))
        ttk.Button(toolbar, text="取消订单", style="Danger.TButton", command=self.do_cancel).pack(
            side="left"
        )
        ttk.Button(
            toolbar, text="改期一晚后", style="Ghost.TButton", command=self.do_reschedule
        ).pack(side="left", padx=8)
        ttk.Button(toolbar, text="刷新", style="Ghost.TButton", command=self.reload).pack(
            side="left"
        )

        self.detail = ttk.Label(
            self,
            text="未选中订单",

            style="Muted.TLabel",
            wraplength=980,
            justify="left",
            anchor="w",
        )
        self.detail.pack(anchor="w", fill="x", pady=(8, 0))
        self.action_message = self.message(self)

        body = ttk.Frame(self, style="Card.TFrame")
        body.pack(fill="both", expand=True, pady=(10, 0))
        self.section(body, "订单列表")
        self.tree = self.table(
            body,
            columns=[
                ("no", "订单号", 95),
                ("hotel", "酒店", 30),
                ("stay", "入住区间", 100),
                ("rooms", "间", 18),
                ("total", "合计", 55),
                ("status", "状态", 45),
            ],
            height=10,
        )
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.on_pick())
        self.list_message = self.message(body)

    def on_show(self) -> None:
        self.reload()

    def reload(self) -> None:
        """列出本人订单（管理员可看全量，这是 S3 交付说明 D2 的既有口径）。"""
        actor = self.session.actor
        if actor is None:
            self.fill(self.tree, [])
            self.set_message(self.list_message, "请先登录", ok=False)
            return
        try:
            bookings = self.session.bookings().list_my_bookings(actor, limit=200)
        except DomainError as error:
            self.set_message(self.list_message, f"读取失败：{error}", ok=False)
            return
        self.fill(
            self.tree,
            [
                (
                    booking.booking_no,
                    f"#{booking.hotel_id}",
                    f"{day_text(booking.check_in_date)} → {day_text(booking.check_out_date)}",
                    booking.room_count,
                    money(booking.total_price_cents),
                    status_text(booking.status.value),
                )
                for booking in bookings
            ],
            raw=bookings,
        )
        self.set_message(self.list_message, f"共 {len(bookings)} 笔订单", ok=True)

    def on_pick(self) -> None:
        """右侧详情：订单号、区间、间数、总价、状态、取消原因。"""
        booking = self.selected_raw(self.tree)
        if booking is None:
            self.detail.configure(text="未选中订单")
            return
        reason = booking.cancel_reason or "—"
        self.detail.configure(
            text=(
                f"订单号 {booking.booking_no}\n"
                f"入住 {day_text(booking.check_in_date)} → {day_text(booking.check_out_date)}"
                f"（{booking.room_count} 间 / {len(booking.nights)} 晚）\n"
                f"合计 {money(booking.total_price_cents)}\n"
                f"状态 {status_text(booking.status.value)}\n"
                f"取消原因 {reason}"
            )
        )

    def do_cancel(self) -> None:
        """顾客取消：只有已确认订单允许（T6），待确认单要等酒店拒单或超时。"""
        booking = self.selected_raw(self.tree)
        if booking is None or self.session.actor is None:
            self.set_message(self.action_message, "请先选中订单并登录", ok=False)
            return
        try:
            updated = self.session.bookings().apply_event(
                booking.booking_no,
                BookingEvent.CANCEL,
                self.session.actor,
                reason=(self.reason.get().strip() or None),
            )
        except DomainError as error:
            self.set_message(self.action_message, f"取消失败：{error}", ok=False)
            return
        self.set_message(
            self.action_message,
            f"已取消 {updated.booking_no}（{status_text(updated.status.value)}）",
            ok=True,
        )
        self.window.set_status(f"已取消 {updated.booking_no}")
        self.reload()

    def do_reschedule(self) -> None:
        """演示用改期：整体后移一晚，日期由订单自身推出，不让用户手填。"""
        booking = self.selected_raw(self.tree)
        if booking is None or self.session.actor is None:
            self.set_message(self.action_message, "请先选中订单并登录", ok=False)
            return
        command = RescheduleCommand(
            new_check_in_date=booking.check_in_date + timedelta(days=1),
            new_check_out_date=booking.check_out_date + timedelta(days=1),
            reason=(self.reason.get().strip() or None),
        )
        try:
            updated = self.session.bookings().reschedule_booking(
                booking.booking_no, command, self.session.actor
            )
        except DomainError as error:
            self.set_message(self.action_message, f"改期失败：{error}", ok=False)
            return
        self.set_message(
            self.action_message,
            f"已改期到 {day_text(updated.check_in_date)} → {day_text(updated.check_out_date)}",
            ok=True,
        )
        self.window.set_status(f"已改期 {updated.booking_no}")
        self.reload()

    def show_today(self) -> date:
        """给后续页面复用的「今天」口径（与对账/报表一致，取本地日历日）。"""
        return date.today()
