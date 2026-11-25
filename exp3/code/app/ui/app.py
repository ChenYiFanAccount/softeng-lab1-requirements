"""主窗口：左侧导航 + 内容区 + 底部状态栏。

十条屏幕在这里登记，``ui_smoke.py`` 也从 ``SCREENS`` 取名字逐个构造——
这样"冒烟列全 10 屏"和"界面真的有 10 屏"是同一份清单，不会各说各话。
"""

from __future__ import annotations

import sqlite3
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from app.domain.enums import ActorRole
from app.infrastructure.db.connection import connect, default_db_path
from app.ui import theme
from app.ui.screens.admin import AdminScreen
from app.ui.screens.audit import AuditScreen
from app.ui.screens.base import BaseScreen
from app.ui.screens.hotel_console import HotelConsoleScreen
from app.ui.screens.inventory_admin import InventoryScreen
from app.ui.screens.login import LoginScreen
from app.ui.screens.my_orders import MyOrdersScreen
from app.ui.screens.reconcile import ReconcileScreen
from app.ui.screens.reports import ReportScreen
from app.ui.screens.results import ResultsScreen
from app.ui.screens.search import SearchScreen
from app.ui.session import Session

ANY: frozenset[ActorRole] = frozenset()
CUSTOMER = frozenset({ActorRole.CUSTOMER})
STAFF = frozenset({ActorRole.HOTEL_STAFF})
ADMIN = frozenset({ActorRole.PLATFORM_ADMIN})


@dataclass(frozen=True, slots=True)
class ScreenSpec:
    """一条屏幕的登记项：键、导航文案、类、可见角色（空集表示游客可见）。"""

    key: str
    label: str
    factory: Callable[[ttk.Frame, "MainWindow"], BaseScreen]
    roles: frozenset[ActorRole] = ANY


SCREENS: tuple[ScreenSpec, ...] = (
    ScreenSpec("login", "登录 / 注册", LoginScreen),
    ScreenSpec("search", "酒店搜索", SearchScreen),
    ScreenSpec("results", "搜索结果", ResultsScreen),
    ScreenSpec("my_orders", "我的订单", MyOrdersScreen, CUSTOMER),
    ScreenSpec("hotel_console", "酒店订单台", HotelConsoleScreen, STAFF | ADMIN),
    ScreenSpec("inventory", "库存与房价", InventoryScreen, STAFF),
    ScreenSpec("audit", "审计日志", AuditScreen, STAFF | ADMIN),
    ScreenSpec("reconcile", "库存对账", ReconcileScreen, STAFF | ADMIN),
    ScreenSpec("admin", "平台管理", AdminScreen, ADMIN),
    ScreenSpec("reports", "经营报表", ReportScreen, STAFF | ADMIN),
)

SCREEN_NAMES: tuple[str, ...] = tuple(spec.label for spec in SCREENS)


class MainWindow(tk.Tk):  # pylint: disable=too-many-instance-attributes
    """应用主窗口；``show(key)`` 切屏，屏幕实例懒建后缓存。"""

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title("酒店预订管理系统 · 软件实现与构建（实验三）")
        self.geometry("1180x740")
        self.minsize(1024, 680)
        theme.apply_theme(self)
        self.configure(background=theme.BG)

        self._screens: dict[str, BaseScreen] = {}
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._current: str | None = None

        self._build_layout()
        self.refresh_nav()
        self.show("login")

    # ── 布局 ──────────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=196)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        title = ttk.Label(self.sidebar, text="酒店预订管理", style="SidebarTitle.TLabel")
        title.pack(anchor="w", padx=16, pady=(20, 2))
        ttk.Label(self.sidebar, text="实验三 · 软件实现与构建", style="SidebarHint.TLabel").pack(
            anchor="w", padx=16, pady=(0, 16)
        )
        self.nav_container = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        self.nav_container.pack(fill="both", expand=True, padx=8)

        right = ttk.Frame(self, style="App.TFrame")
        right.pack(side="left", fill="both", expand=True)

        self.identity = ttk.Label(right, text="未登录", style="Muted.TLabel")
        self.identity.pack(anchor="e", padx=18, pady=(12, 0))

        self.body = ttk.Frame(right, style="App.TFrame")
        self.body.pack(fill="both", expand=True, padx=18, pady=(6, 6))

        self.status_var = tk.StringVar(value="就绪")
        status = ttk.Label(right, textvariable=self.status_var, style="Status.TLabel")
        status.pack(fill="x", side="bottom")

    def refresh_nav(self) -> None:
        """按当前角色重建导航；没登录时只留游客可见的屏。"""
        for child in self.nav_container.winfo_children():
            child.destroy()
        self._nav_buttons.clear()
        actor = self.session.actor
        role = None if actor is None else actor.role
        for spec in SCREENS:
            if spec.roles and (role is None or role not in spec.roles):
                continue
            button = ttk.Button(
                self.nav_container,
                text=spec.label,
                style="Nav.TButton",
                command=lambda key=spec.key: self.show(key),
            )
            button.pack(fill="x", pady=2)
            self._nav_buttons[spec.key] = button
        self.identity.configure(
            text="未登录" if actor is None else f"{actor.login_name}（{actor.role.label}）"
        )
        if self._current is not None:
            self._highlight(self._current)

    def show(self, key: str) -> None:
        """切屏：首次进入才构造，之后只 ``on_show`` 刷新。"""
        spec = _spec(key)
        if spec is None:
            raise KeyError(f"未登记的屏幕：{key}")
        if key not in self._screens:
            screen = spec.factory(self.body, self)
            self._screens[key] = screen
        for other_key, screen in self._screens.items():
            if other_key != key:
                screen.pack_forget()
        self._screens[key].pack(fill="both", expand=True)
        self._current = key
        self._highlight(key)
        self._screens[key].on_show()

    def _highlight(self, key: str) -> None:
        for nav_key, button in self._nav_buttons.items():
            button.configure(style="NavActive.TButton" if nav_key == key else "Nav.TButton")

    def set_status(self, text: str) -> None:
        """底部状态栏一行提示。"""
        self.status_var.set(text)


def _spec(key: str) -> ScreenSpec | None:
    for spec in SCREENS:
        if spec.key == key:
            return spec
    return None


def run(db_path: str | None = None, conn: sqlite3.Connection | None = None) -> int:
    """启动界面；``db_path`` 为 None 用配置里的默认库，``conn`` 可由调用方预先建好。"""
    own_conn = conn is None
    connection = conn if conn is not None else connect(db_path or default_db_path())
    window = MainWindow(Session(conn=connection))
    try:
        window.mainloop()
    finally:
        if own_conn:
            connection.close()
    return 0


def open_connection(db_path: str | None = None) -> sqlite3.Connection:
    """给冒烟脚本用：拿到与 ``run`` 相同的连接配置。"""
    return connect(db_path or default_db_path())
