"""屏 9：平台管理（酒店审核 + 账号查看）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.domain.errors import DomainError
from app.ui.format import audit_status_text, role_text
from app.ui.screens.base import BaseScreen


class AdminScreen(BaseScreen):
    """左侧酒店列表与审核按钮，右侧账号列表。"""

    TITLE = "平台管理"
    SUBTITLE = "只有平台管理员能审核酒店；驳回必须写理由（422 会被拦在按钮前）。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, pady=(12, 0))
        hotels_tab = ttk.Frame(tabs, style="Card.TFrame")
        accounts_tab = ttk.Frame(tabs, style="Card.TFrame")
        tabs.add(hotels_tab, text="  酒店审核  ")
        tabs.add(accounts_tab, text="  账号  ")

        self.section(hotels_tab, "酒店与审核状态")
        self.reason = tk.StringVar()
        line = ttk.Frame(hotels_tab, style="Card.TFrame")
        line.pack(anchor="w", fill="x", pady=(6, 0))
        self.entry_row(line, "驳回理由", var=self.reason, width=28).pack(side="left")
        ttk.Button(line, text="通过审核", style="Primary.TButton", command=self.do_approve).pack(
            side="left", padx=8
        )
        ttk.Button(line, text="驳回", style="Danger.TButton", command=self.do_reject).pack(
            side="left"
        )
        ttk.Button(line, text="刷新", style="Ghost.TButton", command=self.reload).pack(
            side="left", padx=8
        )
        self.message_label = self.message(hotels_tab)
        self.tree = self.table(
            hotels_tab,
            columns=[
                ("id", "ID", 60),
                ("status", "审核状态", 110),
                ("name", "酒店", 180),
                ("address", "地址", 320),
            ],
            height=8,
        )
        self.tree.bind("<<TreeviewSelect>>", lambda event: self.on_pick())

        self.section(accounts_tab, "账号")
        self.hint(accounts_tab, "员工账号与管理员账号由种子数据预置，界面只读。").pack(
            anchor="w", pady=(6, 6)
        )
        self.accounts = self.table(
            accounts_tab,
            columns=[
                ("id", "ID", 60),
                ("login", "登录名", 150),
                ("role", "角色", 110),
                ("hotel", "所属酒店", 110),
                ("status", "状态", 100),
            ],
            height=8,
        )

    def on_show(self) -> None:
        self.reload()

    def reload(self) -> None:
        """酒店按「待审核优先」排序，账号按角色排序。"""
        try:
            hotels = self.session.admin().list_hotels()
            accounts = self.session.admin().list_accounts()
        except DomainError as error:
            self.set_message(self.message_label, f"读取失败：{error}", ok=False)
            return
        self.fill(
            self.tree,
            [
                (row.hotel_id, audit_status_text(row.audit_status), row.name, row.address or "—")
                for row in hotels
            ],
            raw=hotels,
        )
        self.fill(
            self.accounts,
            [
                (
                    row.account_id,
                    row.login_name,
                    role_text(row.role),
                    row.hotel_id if row.hotel_id is not None else "—",
                    row.status,
                )
                for row in accounts
            ],
            raw=accounts,
        )
        pending = len([row for row in hotels if row.audit_status == "PENDING"])
        self.set_message(
            self.message_label, f"共 {len(hotels)} 家酒店，其中待审核 {pending} 家", ok=True
        )

    def on_pick(self) -> None:
        """选中酒店时把审核状态与驳回理由铺到控件上。"""
        row = self.selected_raw(self.tree)
        if row is None:
            return
        self.reason.set(row.reject_reason or "")

    def do_approve(self) -> None:
        """通过审核：写审计 ``HOTEL_APPROVED``。"""
        self._decide(True)

    def do_reject(self) -> None:
        """驳回：理由为空会被服务层拦成 422。"""
        self._decide(False)

    def _decide(self, approve: bool) -> None:
        row = self.selected_raw(self.tree)
        actor = self.session.actor
        if row is None or actor is None:
            self.set_message(self.message_label, "请先选中酒店并登录", ok=False)
            return
        try:
            if approve:
                outcome = self.session.admin().approve(row.hotel_id, actor)
            else:
                outcome = self.session.admin().reject(
                    row.hotel_id, actor, self.reason.get().strip()
                )
        except DomainError as error:
            self.set_message(self.message_label, f"操作失败：{error}", ok=False)
            return
        self.set_message(
            self.message_label,
            f"{row.name} → {audit_status_text(outcome.audit_status)}",
            ok=True,
        )
        self.window.set_status(f"审核完成：{row.name}")
        self.reload()
