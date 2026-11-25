"""屏 1：登录与注册。

演示账号口令统一 ``Passw0rd!``（种子数据），界面上给出提示，避免答辩时现查文档。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.domain.errors import DomainError
from app.ui.screens.base import BaseScreen

DEMO_HINT = "演示账号：13800000000 管理员 / 13800000001 顾客 / 13800000002 酒店店长，口令均为 Passw0rd!"
REGISTER_HINT = "注册只开通顾客账号；员工账号由平台管理员创建。"


class LoginScreen(BaseScreen):
    """登录与注册分两个页签，登录成功后在顶栏显示身份。"""

    TITLE = "登录 / 注册"
    SUBTITLE = "手机号即登录名；注册后可直接用新账号下单。"

    def build(self) -> None:
        self.head().pack(anchor="w", fill="x")

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, pady=(12, 0))

        login_tab = ttk.Frame(tabs, style="Card.TFrame")
        register_tab = ttk.Frame(tabs, style="Card.TFrame")
        tabs.add(login_tab, text="  已有账号  ")
        tabs.add(register_tab, text="  注册新顾客  ")

        self.section(login_tab, "登录")
        self.login_phone = tk.StringVar(value="13800000001")
        self.login_password = tk.StringVar(value="Passw0rd!")
        form = ttk.Frame(login_tab, style="Card.TFrame")
        form.pack(anchor="w", pady=(6, 0))
        self.entry_row(form, "手机号", var=self.login_phone).pack(anchor="w", pady=4)
        self.entry_row(form, "密码", var=self.login_password, show="*").pack(anchor="w", pady=4)
        actions = ttk.Frame(login_tab, style="Card.TFrame")
        actions.pack(anchor="w", pady=(10, 0))
        ttk.Button(actions, text="登录", style="Primary.TButton", command=self.do_login).pack(
            side="left"
        )
        ttk.Button(actions, text="登出", style="Ghost.TButton", command=self.do_logout).pack(
            side="left", padx=8
        )
        self.login_message = self.message(login_tab)
        self.hint(login_tab, DEMO_HINT).pack(anchor="w", pady=(6, 0))

        self.section(register_tab, "注册")
        self.reg_phone = tk.StringVar()
        self.reg_password = tk.StringVar()
        self.reg_confirm = tk.StringVar()
        reg_form = ttk.Frame(register_tab, style="Card.TFrame")
        reg_form.pack(anchor="w", pady=(6, 0))
        self.entry_row(reg_form, "手机号", var=self.reg_phone).pack(anchor="w", pady=4)
        self.entry_row(reg_form, "密码", var=self.reg_password, show="*").pack(anchor="w", pady=4)
        self.entry_row(reg_form, "确认密码", var=self.reg_confirm, show="*").pack(
            anchor="w", pady=4
        )
        ttk.Button(
            register_tab, text="注册", style="Primary.TButton", command=self.do_register
        ).pack(anchor="w", pady=(10, 0))
        self.reg_message = self.message(register_tab)
        self.hint(register_tab, REGISTER_HINT).pack(anchor="w", pady=(6, 0))

    def do_login(self) -> None:
        """调 ``Session.login``；失败把异常文案原样显示。"""
        try:
            actor = self.session.login(self.login_phone.get(), self.login_password.get())
        except DomainError as error:
            self.set_message(self.login_message, f"登录失败：{error}", ok=False)
            return
        self.refresh()
        self.window.set_status(f"已登录：{actor.login_name}")
        self.window.refresh_nav()
        self.window.show("search")

    def do_logout(self) -> None:
        """登出并回到登录页。"""
        self.session.logout()
        self.window.refresh_nav()
        self.window.set_status("已登出")
        self.window.show("login")

    def do_register(self) -> None:
        """注册成功后把手机号填回登录框。"""
        try:
            actor = self.session.accounts().register(
                self.reg_phone.get(), self.reg_password.get(), self.reg_confirm.get()
            )
        except DomainError as error:
            self.set_message(self.reg_message, f"注册失败：{error}", ok=False)
            return
        self.login_phone.set(actor.login_name)
        for var in (self.reg_phone, self.reg_password, self.reg_confirm):
            var.set("")
        self.set_message(self.reg_message, "注册成功，可以直接登录。", ok=True)
