"""屏 8：对账（复用 ``ReconcileService``，界面不自己算差额）。"""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.domain.errors import DomainError
from app.ui.screens.base import BaseScreen

DEFAULT_DAYS = 30


class ReconcileScreen(BaseScreen):
    """左右两侧各算一遍再比对，差异列表原样展示 ``alert_line``。"""

    TITLE = "库存对账"
    SUBTITLE = "左侧读库存表、右侧读订单逐晚快照；两侧独立查询，差异只报告不自动改。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        filter_bar = ttk.Frame(self, style="Card.TFrame")
        filter_bar.pack(fill="x", pady=(12, 0))
        ttk.Label(filter_bar, text="对账天数（从明天起）", style="Body.TLabel").pack(side="left")
        self.days = tk.StringVar(value=str(DEFAULT_DAYS))
        ttk.Entry(filter_bar, textvariable=self.days, width=6).pack(side="left", padx=8)
        ttk.Button(filter_bar, text="立即对账", style="Primary.TButton", command=self.run_check).pack(
            side="left"
        )
        self.summary = ttk.Label(filter_bar, text="尚未对账", style="Muted.TLabel")
        self.summary.pack(side="left", padx=12)

        self.tree = self.table(
            self,
            columns=[
                ("room", "房型", 70),
                ("day", "日期", 110),
                ("inventory", "库存侧", 80),
                ("orders", "订单侧", 80),
                ("diff", "差额", 60),
                ("bookings", "涉及订单", 240),
            ],
            height=13,
        )
        self.tree.pack(fill="both", expand=True, pady=(10, 0))

        self.message_label = self.message(self)

    def on_show(self) -> None:
        self.set_message(self.message_label, "点「立即对账」复用 ReconcileService.check()。", ok=True)

    def run_check(self) -> None:
        """按输入天数对账；差异为 0 时表格清空并显示 ``status=OK``。"""
        try:
            days = int(self.days.get().strip() or str(DEFAULT_DAYS))
        except ValueError:
            self.set_message(self.message_label, "天数必须是整数", ok=False)
            return
        start = date.today() + timedelta(days=1)
        end = start + timedelta(days=days)
        actor = self.session.actor
        hotel_id = None if actor is None or actor.is_admin else actor.hotel_id
        try:
            report = self.session.reconcile().check(start, end, hotel_id)
        except DomainError as error:
            self.set_message(self.message_label, f"对账失败：{error}", ok=False)
            return
        self.fill(
            self.tree,
            [
                (
                    difference.room_type_id,
                    difference.stay_date.isoformat(),
                    difference.inventory_occupied,
                    difference.orders_occupied,
                    difference.diff,
                    ", ".join(difference.booking_nos) or "—",
                )
                for difference in report.differences
            ],
            raw=report.differences,
        )
        state = "平账" if report.is_clean else f"{len(report.differences)} 处差异"
        self.summary.configure(text=f"{start} → {end}：{state}")
        self.set_message(
            self.message_label,
            f"checked_pairs={report.checked_pairs} diff={report.diff_total} "
            f"（{state}）",
            ok=report.is_clean,
        )
        self.window.set_status(f"对账完成：{state}")
