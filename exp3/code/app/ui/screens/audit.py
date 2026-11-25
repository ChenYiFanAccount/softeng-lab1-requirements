"""屏 7：审计日志（只读列表，按对象筛选）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.domain.errors import DomainError
from app.ui.format import event_text, moment_text, role_text, status_text
from app.ui.screens.base import BaseScreen

TARGET_TYPES = ("BOOKING", "HOTEL", "ROOM_INVENTORY", "ACCOUNT")
DEFAULT_LIMIT = 200


class AuditScreen(BaseScreen):
    """审计只追加：本页不提供任何修改/删除入口。"""

    TITLE = "审计日志"
    SUBTITLE = "只读；失败的操作也会留痕（action 前缀 DENIED / REJECTED）。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        toolbar = ttk.Frame(self, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(12, 0))
        ttk.Label(toolbar, text="对象类型", style="Body.TLabel").pack(side="left")
        self.target_type = tk.StringVar(value="BOOKING")
        box = ttk.Combobox(
            toolbar, textvariable=self.target_type, width=16, state="readonly", values=TARGET_TYPES
        )
        box.pack(side="left", padx=8)
        ttk.Label(toolbar, text="对象 ID", style="Body.TLabel").pack(side="left")
        self.target_id = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.target_id, width=24).pack(
            side="left", padx=8
        )
        ttk.Button(
            toolbar, text="查询", style="Primary.TButton", command=self.reload
        ).pack(side="left")
        self.count_label = ttk.Label(toolbar, text="", style="Muted.TLabel")
        self.count_label.pack(side="left", padx=12)

        self.tree = self.table(
            self,
            columns=[
                ("time", "时间", 150),
                ("operator", "操作者", 110),
                ("role", "角色", 80),
                ("action", "动作", 150),
                ("before", "前", 90),
                ("after", "后", 90),
            ],
            height=14,
        )
        self.tree.pack(fill="both", expand=True, pady=(10, 0))
        self.message_label = self.message(self)

    def on_show(self) -> None:
        self.reload()

    def reload(self) -> None:
        """按对象取最近 200 条；对象 ID 留空则只按类型过滤。"""
        try:
            logs = self.session.audit().query(
                self.target_type.get(), self.target_id.get().strip(), limit=DEFAULT_LIMIT
            )
        except DomainError as error:
            self.set_message(self.message_label, f"查询失败：{error}", ok=False)
            return
        self.fill(
            self.tree,
            [
                (
                    moment_text(log.created_at),
                    log.operator_id,
                    role_text(log.operator_role),
                    event_text(log.action),
                    status_text(log.before_state) if log.before_state else "—",
                    status_text(log.after_state) if log.after_state else "—",
                )
                for log in logs
            ],
            raw=logs,
        )
        self.count_label.configure(text=f"共 {len(logs)} 条")
        self.set_message(self.message_label, f"当前显示 {len(logs)} 条（上限 {DEFAULT_LIMIT}）", ok=True)
