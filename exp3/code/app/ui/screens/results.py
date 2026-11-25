"""屏 3：搜索结果 + 房型详情下单（同屏两栏，避免来回跳转丢条件）。"""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from typing import NamedTuple
from tkinter import ttk

from app.application.catalog_service import RoomTypeCard
from app.application.commands import PlaceBookingCommand
from app.domain.errors import DomainError
from app.ui.format import money, status_text
from app.ui.screens.base import BaseScreen

DEFAULT_DAYS = 1


class RoomRow(NamedTuple):
    """把「酒店名 + 房型卡片」拼成表格一行；只做展示，不含业务判断。"""

    hotel_name: str
    card: RoomTypeCard


class ResultsScreen(BaseScreen):
    """左列酒店与房型，右列下单表单。"""

    TITLE = "搜索结果"
    SUBTITLE = "在上方填入住间数并提交；余量按区间逐日最小值计算。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        form = ttk.Frame(self, style="Card.TFrame")
        form.pack(fill="x", pady=(12, 0))
        self.section(form, "下单")
        line = ttk.Frame(form, style="Card.TFrame")
        line.pack(anchor="w", fill="x")
        self.rooms = tk.StringVar(value="1")
        self.entry_row(line, "间数", var=self.rooms, width=6).pack(side="left", padx=(0, 10))
        self.idempotency = tk.StringVar()
        self.entry_row(line, "幂等键", var=self.idempotency, width=20).pack(
            side="left", padx=(0, 10)
        )
        self.remark = tk.StringVar()
        self.entry_row(line, "备注", var=self.remark, width=20).pack(side="left", padx=(0, 10))
        ttk.Button(line, text="提交订单", style="Primary.TButton", command=self.do_place).pack(
            side="left"
        )
        ttk.Button(line, text="回搜索", style="Ghost.TButton", command=self.back).pack(
            side="left", padx=8
        )

        self.detail = ttk.Label(
            self, text="未选中房型", style="Muted.TLabel", wraplength=980, justify="left"
        )
        self.detail.pack(anchor="w", fill="x", pady=(8, 0))
        self.order_message = self.message(self)

        body = ttk.Frame(self, style="Card.TFrame")
        body.pack(fill="both", expand=True, pady=(10, 0))
        self.section(body, "可订房型")
        self.tree = self.table(
            body,
            columns=[
                ("hotel", "酒店", 150),
                ("room", "房型", 130),
                ("price", "起价", 90),
                ("remaining", "余量", 70),
                ("capacity", "可住", 60),
            ],
            height=10,
        )
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.on_pick())
        self.list_message = self.message(body)

    def on_show(self) -> None:
        self.reload()

    def dates(self) -> tuple[date, date]:
        """取搜索页记下的区间；缺失或格式不对就退回「明天 → 后天」。"""
        tomorrow = date.today() + timedelta(days=1)
        raw_in = self.session.recall("check_in", tomorrow.isoformat())
        raw_out = self.session.recall("check_out", (tomorrow + timedelta(days=1)).isoformat())
        try:
            check_in = date.fromisoformat(str(raw_in))
            check_out = date.fromisoformat(str(raw_out))
        except ValueError as error:
            raise DomainError("日期请填 YYYY-MM-DD 格式") from error
        if check_out <= check_in:
            raise DomainError("退房日期必须晚于入住日期")
        return check_in, check_out

    def reload(self) -> None:
        """先按关键词查酒店，再逐个取房型；界面只做扁平化，不拼 SQL。"""
        keyword = self.session.recall("keyword", "") or ""
        check_in, check_out = self.dates()
        try:
            hotels = self.session.catalog().search(keyword, check_in, check_out)
        except DomainError as error:
            self.set_message(self.list_message, f"查询失败：{error}", ok=False)
            return
        rows: list[RoomRow] = []
        for hotel in hotels:
            detail = self.session.catalog().detail(hotel.hotel_id, check_in, check_out)
            if detail is None:
                continue
            for card in detail.room_types:
                rows.append(RoomRow(hotel.name, card))
        self.fill(
            self.tree,
            [
                (
                    row.hotel_name,
                    row.card.name,
                    money(row.card.min_price_cents),
                    row.card.remaining,
                    row.card.capacity,
                )
                for row in rows
            ],
            raw=rows,
        )
        self.set_message(
            self.list_message,
            f"{check_in} → {check_out}：{len(hotels)} 家酒店、{len(rows)} 个可订房型",
            ok=True,
        )

    def on_pick(self) -> None:
        """把选中房型的细节铺到右侧。"""
        row: RoomRow | None = self.selected_raw(self.tree)
        if row is None:
            self.detail.configure(text="未选中房型")
            return
        card = row.card
        self.detail.configure(
            text=(
                f"{row.hotel_name} · {card.name}\n"
                f"床型 {card.bed_type or '—'}，可住 {card.capacity} 人\n"
                f"总房量 {card.total_rooms}，当前余量 {card.remaining}\n"
                f"起价 {money(card.min_price_cents)} / 晚"
            )
        )

    def do_place(self) -> None:
        """提交订单：成功后留在本页刷新余量，并提示订单号。"""
        row: RoomRow | None = self.selected_raw(self.tree)
        if row is None:
            self.set_message(self.order_message, "请先在左侧选中一个房型", ok=False)
            return
        actor = self.session.actor
        if actor is None:
            self.set_message(self.order_message, "请先登录再下单", ok=False)
            return
        try:
            rooms = int(self.rooms.get().strip() or "0")
        except ValueError:
            self.set_message(self.order_message, "间数必须是整数", ok=False)
            return
        check_in, check_out = self.dates()
        command = PlaceBookingCommand(
            guest_id=actor.account_id,
            hotel_id=row.card.hotel_id,
            room_type_id=row.card.room_type_id,
            check_in_date=check_in,
            check_out_date=check_out,
            room_count=rooms,
            idempotency_key=(self.idempotency.get().strip() or None),
            remark=(self.remark.get().strip() or None),
        )
        try:
            booking = self.session.bookings().place_booking(command, actor)
        except DomainError as error:
            self.set_message(self.order_message, f"下单失败：{error}", ok=False)
            return
        self.set_message(
            self.order_message,
            f"下单成功：{booking.booking_no}（{status_text(booking.status.value)}，"
            f"合计 {money(booking.total_price_cents)}）",
            ok=True,
        )
        self.window.set_status(f"已下单 {booking.booking_no}")
        self.reload()

    def back(self) -> None:
        """回搜索页改条件。"""
        self.window.show("search")
