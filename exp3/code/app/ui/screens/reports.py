"""屏 10：经营报表（入住率 / 营收 / 订单状态），数字全部来自 ``ReportService``。"""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.domain.errors import DomainError
from app.ui.format import money, permille, status_text
from app.ui.screens.base import BaseScreen

DEFAULT_DAYS = 30


class ReportScreen(BaseScreen):
    """三张表：逐日入住率、逐日营收、状态分布；顶部一条汇总。"""

    TITLE = "经营报表"
    SUBTITLE = "入住率用千分比整数，营收按逐晚「当时价」累加；界面不做二次加工。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        filter_bar = ttk.Frame(self, style="Card.TFrame")
        filter_bar.pack(fill="x", pady=(12, 0))
        ttk.Label(filter_bar, text="天数（从明天起）", style="Body.TLabel").pack(side="left")
        self.days = tk.StringVar(value=str(DEFAULT_DAYS))
        ttk.Entry(filter_bar, textvariable=self.days, width=6).pack(side="left", padx=8)
        ttk.Button(filter_bar, text="生成报表", style="Primary.TButton", command=self.run_report).pack(
            side="left"
        )
        self.summary = ttk.Label(filter_bar, text="尚未生成", style="Muted.TLabel")
        self.summary.pack(side="left", padx=12)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, pady=(10, 0))

        self.occupancy = self._tab(
            "入住率",
            [("day", "日期", 110), ("sold", "卖出间夜", 90), ("available", "可售间夜", 90),
             ("rate", "入住率", 90)],
        )
        self.revenue = self._tab(
            "营收", [("day", "日期", 110), ("nights", "间夜", 80), ("cents", "营收", 110)]
        )
        self.status = self._tab(
            "订单状态", [("code", "状态", 110), ("count", "订单数", 80)]
        )
        self.message_label = self.message(self)

    def _tab(self, title: str, columns: list[tuple[str, str, int]]) -> ttk.Treeview:
        frame = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(frame, text=title)
        tree = self.table(frame, columns=columns, height=10)
        tree.pack(fill="both", expand=True)
        return tree

    def on_show(self) -> None:
        self.set_message(self.message_label, "点「生成报表」调用 ReportService。", ok=True)

    def run_report(self) -> None:
        """一次取三段数据；任何一段失败都整体提示，不显示半张表。"""
        try:
            days = int(self.days.get().strip() or str(DEFAULT_DAYS))
        except ValueError:
            self.set_message(self.message_label, "天数必须是整数", ok=False)
            return
        start = date.today() + timedelta(days=1)
        end = start + timedelta(days=days)
        actor = self.session.actor
        hotel_id = None if actor is None or actor.is_admin else actor.hotel_id
        service = self.session.reports()
        try:
            occupancy = service.occupancy_by_day(start, end, hotel_id)
            revenue = service.revenue_by_day(start, end, hotel_id)
            counts = service.status_counts(hotel_id)
            summary = service.summary(start, end, hotel_id)
        except DomainError as error:
            self.set_message(self.message_label, f"生成失败：{error}", ok=False)
            return
        self.fill(
            self.occupancy,
            [
                (str(row.stay_date), row.sold_room_nights,
                 row.available_room_nights, permille(row.occupancy_permille))
                for row in occupancy
            ],
        )
        self.fill(
            self.revenue,
            [(str(row.stay_date), row.room_nights, money(row.revenue_cents)) for row in revenue],
        )
        self.fill(
            self.status,
            [(status_text(code), value) for code, value in sorted(counts.items())],
        )
        self.summary.configure(
            text=(
                f"入住率 {permille(summary.occupancy_permille)} · 营收 {money(summary.revenue_cents)}"
                f" · 订单 {summary.order_total} 笔（取消 {summary.cancelled_orders}）"
            )
        )
        self.set_message(
            self.message_label, f"{start} → {end}：{len(occupancy)} 天、{len(revenue)} 行营收", ok=True
        )
        self.window.set_status("报表已生成")
