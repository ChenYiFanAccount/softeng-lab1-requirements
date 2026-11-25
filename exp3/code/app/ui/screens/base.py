"""屏幕基类与几个共用小部件（标题、表格、表单行）。

约定：每个屏幕只做三件事——``build()`` 摆控件、``refresh()`` 从服务取数填进去、
``on_show()`` 决定可见性。取数一律通过 ``self.session`` 的领域/应用服务。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable, Sequence

from app.ui import theme
from app.ui.format import PLACEHOLDER

ColumnSpec = tuple[str, str, int]


class BaseScreen(ttk.Frame):
    """所有屏幕的父类。"""

    TITLE = "未命名"
    SUBTITLE = ""

    def __init__(self, master: tk.Misc, window: Any) -> None:
        super().__init__(master, style="Card.TFrame", padding=(18, 14))
        self.window = window
        self.session = window.session
        self.build()

    # ── 子类实现 ──────────────────────────────────────────────────────
    def build(self) -> None:
        """摆控件；子类必须覆盖。"""
        raise NotImplementedError

    def refresh(self) -> None:
        """从服务重新取数；默认什么都不做（静态屏幕）。"""

    def on_show(self) -> None:
        """切换到本屏时刷新一次；需要登录的屏幕在这里兜权限。"""
        self.refresh()

    # ── 常用助手 ──────────────────────────────────────────────────────
    def head(self, parent: tk.Misc | None = None) -> ttk.Frame:
        """屏幕顶部：标题 + 一句说明。"""
        box = ttk.Frame(parent or self, style="Card.TFrame")
        ttk.Label(box, text=self.TITLE, style="H2.TLabel").pack(anchor="w")
        if self.SUBTITLE:
            ttk.Label(box, text=self.SUBTITLE, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        return box

    def section(self, parent: tk.Misc, text: str) -> ttk.Label:
        """小节标题。"""
        label = ttk.Label(parent, text=text, style="H2.TLabel")
        label.pack(anchor="w", pady=(10, 6))
        return label

    def hint(self, parent: tk.Misc, text: str) -> ttk.Label:
        """灰色说明文字。"""
        label = ttk.Label(parent, text=text, style="Muted.TLabel", wraplength=760, justify="left")
        label.pack(anchor="w", pady=(2, 8))
        return label

    def table(
        self,
        parent: tk.Misc,
        columns: Sequence[ColumnSpec],
        height: int = 12,
        selectmode: str = "browse",
        stretch: bool = True,
    ) -> ttk.Treeview:
        """带滚动条与斑马纹的表格；``columns`` 为 (列 id, 表头, 基准像素宽)。

        ``stretch`` 为真时按"基准宽度占比"把六列铺满表格可视宽度：窗口变宽，
        所有列一起按比例变宽，末列始终留在窗内；窗口缩到 minsize 也按比例收缩，
        但不低于 ``minwidth``。分配由本函数自己算（``<Configure>`` 触发），
        不依赖 ttk 的隐式 stretch，任何 DPI/尺寸下结果都可复现。
        """
        holder = ttk.Frame(parent, style="Card.TFrame")
        holder.pack(fill="both", expand=True, pady=(4, 8))
        tree = ttk.Treeview(
            holder,
            columns=[spec[0] for spec in columns],
            show="headings",
            height=height,
            selectmode=selectmode,
            style="Data.Treeview",
        )
        names = [spec[0] for spec in columns]
        headings = {spec[0]: spec[1] for spec in columns}
        base = {spec[0]: max(40, int(spec[2])) for spec in columns}
        for name in names:
            tree.heading(name, text=headings[name], anchor="w")
            tree.column(name, width=base[name], minwidth=40, anchor="w", stretch=False)

        if stretch:

            def relayout(_event: object = None) -> None:
                # 减 2px：Treeview 左右各有 1px 内边框，不减的话末列右边线会被裁掉
                avail = tree.winfo_width() - 2
                if avail <= 1:
                    return
                weights = sum(base.values())
                widths = {key: max(40, int(avail * base[key] / weights)) for key in names}
                # 舍入误差补给最宽的那列，保证合计恰等于可视宽度、末列不越界
                widest = max(names, key=lambda key: widths[key])
                widths[widest] += avail - sum(widths.values())
                if all(int(tree.column(key, "width")) == widths[key] for key in names):
                    return
                for key in names:
                    tree.column(key, width=widths[key])

            tree.bind("<Configure>", relayout)
            tree.after_idle(relayout)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        tree.tag_configure("zebra", background=theme.ZEBRA)
        return tree

    def fill(
        self,
        tree: ttk.Treeview,
        rows: Iterable[Sequence[Any]],
        raw: Iterable[Any] | None = None,
    ) -> None:
        """清表并填充；``raw`` 与 ``rows`` 一一对应，存进 ``tree.raw`` 供选中取原对象。"""
        for item in tree.get_children():
            tree.delete(item)
        objects = list(raw) if raw is not None else []
        stored: dict[str, Any] = {}
        for position, values in enumerate(rows):
            item = tree.insert(
                "",
                "end",
                values=tuple(PLACEHOLDER if value is None else value for value in values),
                tags=("zebra",) if position % 2 else (),
            )
            if position < len(objects):
                stored[item] = objects[position]
        tree.raw = stored  # type: ignore[attr-defined]

    def selected_raw(self, tree: ttk.Treeview) -> Any:
        """取当前选中行对应的原对象；未选中返回 None。"""
        chosen = tree.selection()
        if not chosen:
            return None
        return getattr(tree, "raw", {}).get(chosen[0])

    def entry_row(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        parent: tk.Misc,
        label: str,
        value: str = "",
        width: int = 24,
        var: tk.StringVar | None = None,
        show: str = "",
    ) -> tuple[ttk.Frame, tk.StringVar]:
        """一行"标签 + 输入框"；返回 (所在行, 变量)。传入 ``var`` 可复用已有变量。"""
        row = ttk.Frame(parent, style="Card.TFrame")
        ttk.Label(row, text=label, style="Body.TLabel", width=10).pack(side="left")
        holder = var if var is not None else tk.StringVar(value=value)
        ttk.Entry(row, textvariable=holder, width=width, show=show).pack(side="left", padx=(0, 10))
        return row

    def message(self, parent: tk.Misc) -> ttk.Label:
        """红色/绿色提示行（成功与失败共用，靠 ``set_message`` 改色）。"""
        label = ttk.Label(parent, text="", style="Muted.TLabel", wraplength=760, justify="left")
        label.pack(anchor="w", pady=(4, 0))
        return label

    @staticmethod
    def set_message(label: ttk.Label, text: str, ok: bool = True) -> None:
        """写提示并改颜色。"""
        label.configure(text=text, foreground=theme.OK if ok else theme.DANGER)
