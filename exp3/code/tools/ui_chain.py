"""S6-5 / S6-R1-04：用真实 Tk 窗口跑一条完整业务链，断言界面与数据一致。

与 ``ui_smoke.py`` 的区别：冒烟只证明"十屏能构造、不抛异常"；本脚本真的
**按按钮**（``ttk.Button.invoke()``）走完 下单 → 确认 → 入住 → 退房，
并在每一步断言数据库状态、界面提示、审计条数，最后校验退房后营收不为零。

判据（``评审记录/S6_第1轮.md`` 的 S6-R1-04）共 8 步：
1. 顾客登录（点「登录」）　2. 搜索（点「搜索」）　3. 下单（点「提交订单」）
4. 我的订单看到"待确认"并选中　5. 顾客点「取消订单」应当被拒（待确认单顾客
无权取消，T6 只从已确认出发）　6. 店长「确认预订」　7. 店长「办理入住」
8. 店长「办理退房」+ 报表营收不为零 + 审计四条。

用法::

    python code/tools/ui_chain.py

退出码 0 = 全部断言通过。
"""

from __future__ import annotations

import ctypes
import sys
import tempfile
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import ttk

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.application.report_service import ReportService  # noqa: E402
from app.domain.enums import BookingStatus  # noqa: E402
from app.infrastructure.db.connection import connect, load_settings  # noqa: E402
from app.infrastructure.db.migrate_runner import apply_migrations  # noqa: E402
from app.infrastructure.db.seed import seed_all  # noqa: E402
from app.ui.app import MainWindow  # noqa: E402
from app.ui.session import Session  # noqa: E402

CUSTOMER_LOGIN = "13800000001"
STAFF_LOGIN = "13800000002"
PASSWORD = "Passw0rd!"


def enable_dpi_awareness() -> None:
    """与截图脚本一致：让 Tk 按物理像素布局，避免按钮被裁到窗外点不到。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
        return
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
    except Exception:  # pylint: disable=broad-exception-caught
        pass


enable_dpi_awareness()


class ChainFailure(AssertionError):
    """断言失败（带步骤号，便于在证据里定位）。"""


def check(condition: bool, message: str) -> None:
    """断言；失败即抛 ``ChainFailure``。"""
    if not condition:
        raise ChainFailure(message)


def button(root: tk.Misc, text: str) -> ttk.Button:
    """按文字找按钮（界面里的按钮都是就地创建，没有属性名）。"""
    stack: list[tk.Misc] = [root]
    while stack:
        widget = stack.pop()
        if isinstance(widget, ttk.Button) and str(widget.cget("text")).strip() == text:
            return widget
        stack.extend(widget.winfo_children())
    raise ChainFailure(f"找不到按钮：{text}")


def click(root: tk.Misc, text: str) -> None:
    """点按钮并让界面把事件处理完。"""
    target = button(root, text)
    target.invoke()
    root.update()


def select_row(root: tk.Misc, tree: ttk.Treeview, index: int = 0) -> None:
    """选中表格第 ``index`` 行并触发 ``<<TreeviewSelect>>``。"""
    children = tree.get_children()
    check(children and len(children) > index, f"表格没有第 {index} 行")
    tree.selection_set(children[index])
    tree.focus(children[index])
    tree.event_generate("<<TreeviewSelect>>")
    root.update()


def select_booking(root: tk.Misc, tree: ttk.Treeview, booking_no: str) -> None:
    """按订单号定位并选中一行——每次动作后表格会 ``reload``，选中态会丢。"""
    for item in tree.get_children():
        values = [str(value) for value in tree.item(item, "values")]
        if booking_no in values:
            tree.selection_set(item)
            tree.focus(item)
            tree.event_generate("<<TreeviewSelect>>")
            root.update()
            return
    raise ChainFailure(f"表格里找不到订单 {booking_no}（共 {len(tree.get_children())} 行）")


def screen(window: MainWindow, key: str) -> tk.Misc:
    """取屏幕对象（懒建，``show`` 之后才存在）。"""
    window.show(key)
    window.update()
    return window._screens[key]  # pylint: disable=protected-access


def booking_row(conn, booking_no: str):
    """直接查库取订单行，用于比"界面说的"和"库里存的"。"""
    return conn.execute(
        "SELECT status, total_price_cents, check_in_date, check_out_date "
        "FROM booking WHERE booking_no = ?",
        (booking_no,),
    ).fetchone()


def audit_actions(conn, booking_no: str) -> list[str]:
    """取该订单的审计动作序列（按时间正序）。"""
    rows = conn.execute(
        "SELECT action FROM audit_log WHERE target_type = 'BOOKING' AND target_id = ? "
        "ORDER BY id",
        (booking_no,),
    ).fetchall()
    return [row["action"] for row in rows]


def latest_booking_no(conn, guest_id: int) -> str:
    """取该顾客最近的订单号。"""
    row = conn.execute(
        "SELECT booking_no FROM booking WHERE guest_id = ? ORDER BY id DESC LIMIT 1",
        (guest_id,),
    ).fetchone()
    check(row is not None, "库里没有订单")
    return str(row["booking_no"])


def run_chain(conn, window: MainWindow) -> list[str]:  # pylint: disable=too-many-locals,too-many-statements
    """走完 8 步，返回每步的结果摘要（写进证据文件）。"""
    steps: list[str] = []
    login_screen = screen(window, "login")

    # ① 顾客登录
    login_screen.login_phone.set(CUSTOMER_LOGIN)  # type: ignore[attr-defined]
    login_screen.login_password.set(PASSWORD)  # type: ignore[attr-defined]
    click(window, "登录")
    actor = window.session.require_actor()
    check(actor.login_name == CUSTOMER_LOGIN, f"登录身份不对：{actor.login_name}")
    steps.append(f"step1 登录 ok actor={actor.login_name} role={actor.role.value}")

    # ② 搜索（条件用后天起两晚，落在种子的 90 天价格窗口内）
    start = date.today() + timedelta(days=2)
    search_screen = screen(window, "search")
    search_screen.keyword.set("")  # type: ignore[attr-defined]
    search_screen.check_in.set(start.isoformat())  # type: ignore[attr-defined]
    search_screen.check_out.set((start + timedelta(days=2)).isoformat())  # type: ignore[attr-defined]
    click(window, "搜索")
    results = screen(window, "results")
    rows = results.tree.get_children()  # type: ignore[attr-defined]
    check(len(rows) > 0, "搜索结果为空（种子数据或日期窗口有问题）")
    steps.append(f"step2 搜索 ok rows={len(rows)} range={start}→{start + timedelta(days=2)}")

    # ③ 选中第一行房型并提交订单
    select_row(window, results.tree)  # type: ignore[attr-defined]
    click(window, "提交订单")
    booking_no = latest_booking_no(conn, actor.account_id)
    row = booking_row(conn, booking_no)
    check(row["status"] == BookingStatus.PENDING.value, f"下单后状态={row['status']}")
    steps.append(
        f"step3 下单 ok booking={booking_no} status={row['status']} total={row['total_price_cents']}"
    )

    # ④ 我的订单里能看到这笔单，且显示待确认
    orders = screen(window, "my_orders")
    select_booking(window, orders.tree, booking_no)  # type: ignore[attr-defined]
    detail_text = str(orders.detail.cget("text"))  # type: ignore[attr-defined]
    check("待确认" in detail_text, f"详情没显示待确认：{detail_text!r}")
    steps.append(f"step4 我的订单 ok detail={detail_text.splitlines()[0]}")

    # ⑤ 顾客点「取消订单」被拒（待确认单顾客无权取消）
    orders.reason.set("顾客想撤单")  # type: ignore[attr-defined]
    click(window, "取消订单")
    message = str(orders.action_message.cget("text"))  # type: ignore[attr-defined]
    after_cancel = booking_row(conn, booking_no)
    check(after_cancel["status"] == BookingStatus.PENDING.value,
          f"顾客越权取消竟然成功：{after_cancel['status']}")
    check("失败" in message or "非法" in message, f"界面没提示拒绝：{message!r}")
    steps.append(f"step5 顾客越权被拒 ok msg={message}")

    # ⑥⑦⑧ 店长：确认 → 入住 → 退房
    window.session.logout()
    window.refresh_nav()
    screen(window, "login")
    window.session.login(STAFF_LOGIN, PASSWORD)
    window.refresh_nav()
    console = screen(window, "hotel_console")

    for event_label, expected in (
        ("确认预订", BookingStatus.CONFIRMED.value),
        ("办理入住", BookingStatus.CHECKED_IN.value),
        ("办理退房", BookingStatus.CHECKED_OUT.value),
    ):
        console.reason.set("")  # type: ignore[attr-defined]
        # 每次动作后订单台会 reload，选中态清零，必须重新按订单号定位。
        select_booking(window, console.tree, booking_no)  # type: ignore[attr-defined]
        click(window, event_label)
        current = booking_row(conn, booking_no)
        check(current["status"] == expected,
              f"{event_label} 后期望 {expected}，实际 {current['status']}")
        steps.append(f"{event_label} ok status={current['status']}")

    # 审计：四条业务动作（CREATE/CONFIRM/CHECK_IN/CHECK_OUT）+ 一条失败留痕
    actions = audit_actions(conn, booking_no)
    succeeded = [a for a in actions if not a.startswith(("DENIED:", "REJECTED:"))]
    check(succeeded == ["CREATE", "CONFIRM", "CHECK_IN", "CHECK_OUT"],
          f"审计业务动作不对：{succeeded}（全量 {actions}）")
    check(any(a.startswith("REJECTED:") for a in actions),
          f"顾客越权那次没有留审计：{actions}")
    steps.append(f"审计 ok 业务4条={succeeded} 失败1条={[a for a in actions if a not in succeeded]}")

    # 退房后营收不为零（退房只改状态、不释放占用，营收必须仍在）
    reports = screen(window, "reports")
    reports.days.set("30")  # type: ignore[attr-defined]
    click(window, "生成报表")
    service = ReportService(conn)
    revenue = service.revenue_by_day(start, start + timedelta(days=2))
    total = sum(item.revenue_cents for item in revenue)
    check(total > 0, f"退房后营收归零：{total}")
    steps.append(f"报表营收 ok total_cents={total}")
    return steps


def main() -> int:
    """建临时库、开真窗口、走链，逐行打印结果。"""
    with tempfile.TemporaryDirectory(prefix="ui-chain-", ignore_cleanup_errors=True) as raw:
        db_path = Path(raw) / "ui_chain.db"
        conn = connect(db_path)
        try:
            apply_migrations(conn)
            seed_all(conn, load_settings())
            window = MainWindow(Session(conn=conn))
            window.geometry("1640x960+10+10")
            window.deiconify()
            window.update()
            try:
                steps = run_chain(conn, window)
            finally:
                window.destroy()
        finally:
            conn.close()

    print("chain_steps=8")
    for line in steps:
        print(line)
    print("check=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
