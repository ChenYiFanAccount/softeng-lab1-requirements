"""屏 6：酒店库存与房价维护。"""

from __future__ import annotations

# pylint: disable=missing-function-docstring  # 按钮回调名即语义，逐个写 docstring 是噪声
import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.domain.errors import DomainError
from app.ui.format import day_text, money
from app.ui.screens.base import BaseScreen

WINDOW_DAYS = 14


class InventoryScreen(BaseScreen):
    """按房型 + 两周窗口列库存，改可售 / 停售 / 改价。"""

    TITLE = "库存与房价"
    SUBTITLE = "展示未来 14 天：改可售房量、停售复售、改单价；每条动作都写审计。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        self.room_types: dict[int, str] = {}
        toolbar = ttk.Frame(self, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(12, 0))
        ttk.Label(toolbar, text="房型", style="Body.TLabel").pack(side="left")
        self.room_choice = tk.StringVar()
        self.room_box = ttk.Combobox(
            toolbar, textvariable=self.room_choice, width=40, state="readonly"
        )
        self.room_box.pack(side="left", padx=8)
        self.room_box.bind("<<ComboboxSelected>>", lambda event: self.reload())
        ttk.Button(toolbar, text="刷新", style="Ghost.TButton", command=self.reload).pack(side="left")

        form = ttk.Frame(self, style="Card.TFrame")
        form.pack(fill="x", pady=(10, 0))
        self.new_available = tk.StringVar()
        self.new_price = tk.StringVar()
        self.entry_row(form, "可售改为", var=self.new_available, width=6).pack(side="left")
        ttk.Button(form, text="改可售", style="Primary.TButton", command=self.do_set_available).pack(
            side="left", padx=8
        )
        self.entry_row(form, "单价改为", var=self.new_price, width=8).pack(side="left", padx=(12, 0))
        ttk.Button(form, text="改价", style="Ghost.TButton", command=self.do_set_price).pack(
            side="left", padx=8
        )
        ttk.Button(form, text="停售", style="Danger.TButton", command=self.do_suspend).pack(
            side="left", padx=(12, 0)
        )
        ttk.Button(form, text="复售", style="Ghost.TButton", command=self.do_resume).pack(
            side="left", padx=8
        )

        self.tree = self.table(
            self,
            columns=[
                ("day", "日期", 110),
                ("available", "可售", 60),
                ("occupied", "已占用", 70),
                ("remaining", "余量", 60),
                ("price", "单价", 90),
                ("sale", "销售状态", 90),
            ],
            height=14,
        )
        self.tree.pack(fill="both", expand=True, pady=(10, 0))

        self.message_label = self.message(self)

    def on_show(self) -> None:
        self.reload()

    def days(self) -> list[date]:
        """未来 14 天（含今天）。"""
        today = date.today()
        return [today + timedelta(days=offset) for offset in range(WINDOW_DAYS)]

    def reload(self) -> None:
        """先填房型下拉框，再按选中房型拉库存行。"""
        actor = self.session.actor
        if actor is None:
            self.set_message(self.message_label, "请先登录", ok=False)
            return
        try:
            hotel_id = self.hotel_id()
            if hotel_id is None:
                self.set_message(self.message_label, "该账号没有归属酒店", ok=False)
                return
            first_day, last_day = self.days()[0], self.days()[-1]
            detail = self.session.catalog().detail(
                hotel_id, first_day, last_day + timedelta(days=1)
            )
        except DomainError as error:
            self.set_message(self.message_label, f"读取房型失败：{error}", ok=False)
            return
        if detail is None:
            self.set_message(self.message_label, "本酒店尚未通过审核，暂不能维护库存", ok=False)
            return
        # 房型清单每次刷新重建；放这里是因为要先有库与登录身份。
        self.room_types = {
            f"{card.name}（#{card.room_type_id}）": card for card in detail.room_types
        }
        labels = list(self.room_types)
        self.room_box.configure(values=labels)
        if not labels:
            self.set_message(self.message_label, "本酒店还没有房型", ok=False)
            return
        if self.room_choice.get() not in labels:
            self.room_choice.set(labels[0])
        self._fill_rows()

    def _fill_rows(self) -> None:
        card = self.room_types.get(self.room_choice.get())
        if card is None:
            return
        inventories = self.session.inventory().range_rows(card.room_type_id, self.days())
        rows = []
        for row in inventories:
            rows.append(
                (
                    day_text(row.stay_date),
                    row.available_rooms,
                    row.occupied_rooms,
                    row.remaining,
                    money(self.session.inventory().current_price(card.room_type_id, row.stay_date)),
                    "停售" if row.sale_status == "SUSPENDED" else "在售",
                )
            )
        self.fill(self.tree, rows, raw=inventories)
        self.set_message(self.message_label, f"{card.name}：{len(rows)} 天", ok=True)

    def hotel_id(self) -> int | None:
        actor = self.session.actor
        return None if actor is None else actor.hotel_id

    def _selected(self):
        row = self.selected_raw(self.tree)
        card = self.room_types.get(self.room_choice.get())
        return (card, row)

    def do_set_available(self) -> None:
        card, row = self._selected()
        if card is None or row is None:
            self.set_message(self.message_label, "请先选中日期行", ok=False)
            return
        try:
            value = int(self.new_available.get().strip())
        except ValueError:
            self.set_message(self.message_label, "可售房量必须是整数", ok=False)
            return
        self._call(
            lambda: self.session.inventory().adjust_available(
                card.room_type_id, row.stay_date, value, self.session.actor
            ),
            f"已改可售为 {value}",
        )

    def do_set_price(self) -> None:
        card, row = self._selected()
        if card is None or row is None:
            self.set_message(self.message_label, "请先选中日期行", ok=False)
            return
        try:
            cents = int(self.new_price.get().strip()) * 100
        except ValueError:
            self.set_message(self.message_label, "单价请填整数元", ok=False)
            return
        self._call(
            lambda: self.session.inventory().set_unit_price(
                card.room_type_id, row.stay_date, cents, self.session.actor
            ),
            f"已改单价为 {money(cents)}",
        )

    def do_suspend(self) -> None:
        card, row = self._selected()
        if card is None or row is None:
            self.set_message(self.message_label, "请先选中日期行", ok=False)
            return
        self._call(
            lambda: self.session.inventory().suspend_day(
                card.room_type_id, row.stay_date, self.session.actor
            ),
            "已停售该日",
        )

    def do_resume(self) -> None:
        card, row = self._selected()
        if card is None or row is None:
            self.set_message(self.message_label, "请先选中日期行", ok=False)
            return
        self._call(
            lambda: self.session.inventory().resume_day(
                card.room_type_id, row.stay_date, self.session.actor
            ),
            "已恢复销售",
        )

    def _call(self, action, ok_text: str) -> None:
        """统一把服务层异常翻译成界面提示，成功后刷新表格。"""
        try:
            action()
        except DomainError as error:
            self.set_message(self.message_label, f"操作失败：{error}", ok=False)
            return
        self.set_message(self.message_label, ok_text, ok=True)
        self.window.set_status(ok_text)
        self._fill_rows()
