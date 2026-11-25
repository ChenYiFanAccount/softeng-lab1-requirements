"""界面主题：一处定义颜色、字体与 ttk 样式，屏幕只引用样式名。

为什么把颜色写成常量而不是散在屏幕里：截图要交 10 张，任何一处色值漂移都会
让报告里的界面看起来像两个程序。改这里，十屏一起变。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#EEF2F7"
SIDEBAR_BG = "#16243A"
SIDEBAR_ACTIVE = "#2F6FEB"
SIDEBAR_TEXT = "#C8D4E4"
CARD_BG = "#FFFFFF"
INK = "#1B2430"
MUTED = "#5B6B7C"
ACCENT = "#2F6FEB"
ACCENT_DARK = "#1E4FB8"
OK = "#1F8A4C"
WARN = "#B26B00"
DANGER = "#C0392B"
LINE = "#D6DEE8"
ZEBRA = "#F7FAFD"

FONT_FAMILY = "Microsoft YaHei UI"
FONT_BODY = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_BOLD = (FONT_FAMILY, 10, "bold")
FONT_H1 = (FONT_FAMILY, 18, "bold")
FONT_H2 = (FONT_FAMILY, 13, "bold")
FONT_NAV = (FONT_FAMILY, 10)


def apply_theme(root: tk.Misc) -> ttk.Style:
    """给 root 挂上统一字体与 ttk 样式；返回样式对象便于测试断言。"""
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(family=FONT_FAMILY, size=10)
        except tk.TclError:  # 无该命名字体时忽略，Windows 上一般不会发生
            continue

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", font=FONT_BODY, background=BG, foreground=INK)
    style.configure("App.TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD_BG, relief="flat")
    style.configure("Sidebar.TFrame", background=SIDEBAR_BG)
    style.configure("Header.TFrame", background=CARD_BG)

    style.configure("H1.TLabel", font=FONT_H1, background=BG, foreground=INK)
    style.configure("H2.TLabel", font=FONT_H2, background=CARD_BG, foreground=INK)
    style.configure("Body.TLabel", background=CARD_BG, foreground=INK)
    style.configure("Muted.TLabel", font=FONT_SMALL, background=CARD_BG, foreground=MUTED)
    style.configure(
        "SidebarTitle.TLabel",
        font=FONT_H2,
        background=SIDEBAR_BG,
        foreground="#FFFFFF",
    )
    style.configure(
        "SidebarHint.TLabel", font=FONT_SMALL, background=SIDEBAR_BG, foreground=SIDEBAR_TEXT
    )

    style.configure(
        "Nav.TButton",
        font=FONT_NAV,
        anchor="w",
        padding=(14, 9),
        background=SIDEBAR_BG,
        foreground=SIDEBAR_TEXT,
        borderwidth=0,
        focusthickness=0,
    )
    style.map(
        "Nav.TButton",
        background=[("active", "#22344F")],
        foreground=[("active", "#FFFFFF")],
    )
    style.configure(
        "NavActive.TButton",
        font=(FONT_FAMILY, 10, "bold"),
        anchor="w",
        padding=(14, 9),
        background=SIDEBAR_ACTIVE,
        foreground="#FFFFFF",
        borderwidth=0,
    )
    style.map("NavActive.TButton", background=[("active", ACCENT_DARK)])

    style.configure(
        "Primary.TButton",
        font=FONT_BOLD,
        padding=(14, 7),
        background=ACCENT,
        foreground="#FFFFFF",
        borderwidth=0,
    )
    style.map("Primary.TButton", background=[("active", ACCENT_DARK), ("disabled", LINE)])

    style.configure(
        "Ghost.TButton", font=FONT_BODY, padding=(12, 6), background=LINE, foreground=INK
    )
    style.map("Ghost.TButton", background=[("active", "#C7D3E2")])

    style.configure(
        "Danger.TButton",
        font=FONT_BOLD,
        padding=(14, 7),
        background=DANGER,
        foreground="#FFFFFF",
    )
    style.map("Danger.TButton", background=[("active", "#9B2C20")])

    style.configure("TEntry", padding=(6, 5), fieldbackground="#FFFFFF")
    style.configure("TCombobox", padding=(6, 4))

    style.configure(
        "Data.Treeview",
        font=FONT_BODY,
        rowheight=26,
        background=CARD_BG,
        fieldbackground=CARD_BG,
        foreground=INK,
        borderwidth=0,
    )
    style.configure(
        "Data.Treeview.Heading",
        font=FONT_BOLD,
        background="#E4EBF4",
        foreground=INK,
        padding=(8, 6),
    )
    style.map("Data.Treeview", background=[("selected", "#CFE0FF")], foreground=[("selected", INK)])
    style.configure(
        "Status.TLabel",
        font=FONT_SMALL,
        background="#E4EBF4",
        foreground=MUTED,
        padding=(14, 6),
    )
    style.configure("TNotebook", background=CARD_BG, borderwidth=0)
    style.configure("TNotebook.Tab", font=FONT_BODY, padding=(14, 7))
    return style
