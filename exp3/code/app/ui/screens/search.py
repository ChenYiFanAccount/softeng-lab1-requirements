"""屏 2：酒店搜索。

只做三件事：收条件（关键词 / 入住日 / 退房日）、校验日期、把条件记进 ``Session`` 后跳结果页。
真正的筛选在 ``CatalogService.search`` 里，界面不碰 SQL。
"""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from app.domain.errors import DomainError
from app.ui.screens.base import BaseScreen


class SearchScreen(BaseScreen):
    """搜索条件页。"""

    TITLE = "酒店搜索"
    SUBTITLE = "按酒店名或地址模糊匹配；日期留空则默认「明天入住、住一晚」。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="x", pady=(12, 0))

        tomorrow = date.today() + timedelta(days=1)
        self.keyword = tk.StringVar(value=self.session.recall("keyword", "") or "")
        self.check_in = tk.StringVar(value=self.session.recall("check_in", tomorrow.isoformat()))
        self.check_out = tk.StringVar(
            value=self.session.recall("check_out", (tomorrow + timedelta(days=1)).isoformat())
        )

        self.entry_row(card, "关键词", var=self.keyword, width=30).pack(anchor="w", pady=4)
        self.entry_row(card, "入住日", var=self.check_in, width=16).pack(anchor="w", pady=4)
        self.entry_row(card, "退房日", var=self.check_out, width=16).pack(anchor="w", pady=4)

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.pack(anchor="w", pady=(10, 0))
        ttk.Button(actions, text="搜索", style="Primary.TButton", command=self.do_search).pack(
            side="left"
        )
        ttk.Button(actions, text="重置", style="Ghost.TButton", command=self.do_reset).pack(
            side="left", padx=8
        )

        self.message_label = self.message(card)
        self.hint(card, "示例：输入「云栖」只匹配云栖酒店；留空则列出全部已审核酒店。").pack(
            anchor="w", pady=(6, 0)
        )

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        actor = self.session.actor
        if actor is None:
            self.set_message(self.message_label, "未登录也可以搜索，但下单前需要登录。", ok=True)
        else:
            self.set_message(self.message_label, f"当前身份：{actor.login_name}", ok=True)

    def do_reset(self) -> None:
        """清空关键词并把日期恢复成明天 / 后天。"""
        tomorrow = date.today() + timedelta(days=1)
        self.keyword.set("")
        self.check_in.set(tomorrow.isoformat())
        self.check_out.set((tomorrow + timedelta(days=1)).isoformat())

    def do_search(self) -> None:
        """校验日期后写进 ``Session``，让结果页自己再去查。"""
        try:
            check_in, check_out = self.parsed_dates()
        except DomainError as error:
            self.set_message(self.message_label, f"日期不合法：{error}", ok=False)
            return
        self.session.remember(
            keyword=self.keyword.get().strip(),
            check_in=check_in.isoformat(),
            check_out=check_out.isoformat(),
        )
        self.window.set_status(f"搜索条件：{check_in} → {check_out}")
        self.window.show("results")

    def parsed_dates(self) -> tuple[date, date]:
        """把两个输入框解析成日期；格式或先后顺序不对就抛 ``ValidationError``。"""
        check_in = _parse_day(self.check_in.get(), "入住日")
        check_out = _parse_day(self.check_out.get(), "退房日")
        if check_out <= check_in:
            raise DomainError("退房日期必须晚于入住日期")
        return check_in, check_out


def _parse_day(text: str, label: str) -> date:
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError as error:
        raise DomainError(f"{label} 请填 YYYY-MM-DD 格式") from error
