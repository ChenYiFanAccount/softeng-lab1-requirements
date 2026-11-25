"""生成 10 张界面截图，供 S6-2 交付与报告引用。

做法：在临时库里铺一套"什么状态都有"的演示数据（待确认 / 已确认 / 已入住 /
已退房 / 已取消 / 未入住），再开真窗口逐屏 ``show`` + ``update``，用
``PIL.ImageGrab`` 截窗口矩形存到 ``docs/screenshots/``。

为什么不手点：10 屏 × 每种状态都要有数据，手点一次要十几分钟且不可复现；
脚本跑一次十几秒，报告里的图与库里的数据能对上。

用法：
    python code/tools/take_screenshots.py             # 写 docs/screenshots
    python code/tools/take_screenshots.py --out tmp   # 换个目录
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = CODE_ROOT.parent
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.application.actor import Actor  # noqa: E402
from app.application.booking_service import BookingAppService  # noqa: E402
from app.application.commands import PlaceBookingCommand  # noqa: E402
from app.domain.enums import ActorRole, BookingEvent  # noqa: E402
from app.infrastructure.db.connection import connect, load_settings  # noqa: E402
from app.infrastructure.db.migrate_runner import apply_migrations  # noqa: E402
from app.infrastructure.db.seed import seed_all  # noqa: E402
from app.ui.app import MainWindow  # noqa: E402
from app.ui.session import Session  # noqa: E402

CUSTOMER_LOGIN = "13800000001"
STAFF_LOGIN = "13800000002"
ADMIN_LOGIN = "13800000000"
PASSWORD = "Passw0rd!"
SHOTS: tuple[tuple[str, str], ...] = (
    ("login", "01_login"),
    ("search", "02_search"),
    ("results", "03_results"),
    ("my_orders", "04_my_orders"),
    ("inventory", "06_inventory"),
    ("hotel_console", "05_hotel_console"),
    ("admin", "09_admin"),
    ("audit", "07_audit"),
    ("reconcile", "08_reconcile"),
    ("reports", "10_reports"),
)


def build_database(base_dir: Path) -> Path:
    """建库、跑迁移、灌种子，再补一批覆盖六种状态的订单。"""
    db_path = base_dir / "screenshots.db"
    conn = connect(db_path)
    try:
        apply_migrations(conn)
        seed_all(conn, load_settings())
        _fill_demo_orders(conn)
    finally:
        conn.close()
    return db_path


def _fill_demo_orders(conn) -> None:  # pylint: disable=too-many-locals
    """下 6 单并推到 6 个状态；用固定日期，截图里不会出现"今天"漂移。"""
    guest = Actor(account_id=2, role=ActorRole.CUSTOMER, login_name=CUSTOMER_LOGIN)
    staff = Actor(account_id=4, role=ActorRole.HOTEL_STAFF, hotel_id=1, login_name=STAFF_LOGIN)
    admin = Actor(account_id=1, role=ActorRole.PLATFORM_ADMIN, login_name=ADMIN_LOGIN)
    service = BookingAppService(conn)
    base = date.today() + timedelta(days=2)
    plan = [
        (BookingEvent.CONFIRM, BookingEvent.CHECK_IN, BookingEvent.CHECK_OUT),
        (BookingEvent.CONFIRM, BookingEvent.CHECK_IN, None),
        (BookingEvent.CONFIRM, BookingEvent.NO_SHOW, None),
        (BookingEvent.CONFIRM, BookingEvent.CANCEL, None),
        (BookingEvent.REJECT, None, None),
        (None, None, None),
    ]
    for index, chain in enumerate(plan):
        check_in = base + timedelta(days=index)
        command = PlaceBookingCommand(
            guest_id=guest.account_id,
            hotel_id=1,
            room_type_id=1 + (index % 2),
            check_in_date=check_in,
            check_out_date=check_in + timedelta(days=2),
            room_count=1 + (index % 2),
        )
        booking = service.place_booking(command, guest)
        for event in chain:
            if event is None:
                continue
            actor = admin if event is BookingEvent.REJECT else staff
            service.apply_event(booking.booking_no, event, actor, reason="演示数据")


def capture(window: MainWindow, target: Path) -> None:
    """截主窗口矩形；先 ``update`` 保证布局与滚动条状态已生效。

    venv 里没有 Pillow（运行期只允许标准库），所以借 Windows 自带的
    ``System.Drawing`` 抓屏：一张约 0.6 s，10 张不到 7 秒。
    """
    window.update_idletasks()
    # 抓屏是按屏幕坐标取的：窗口必须置顶且在桌面前台，否则会拍到别的应用。
    window.attributes("-topmost", True)
    window.lift()
    window.focus_force()
    window.update()
    time.sleep(0.35)
    window.update()
    # Tk 的坐标与尺寸都是逻辑单位，屏幕抓取要的是物理像素：差一个 DPI 系数。
    scale = _dpi_scale(window)
    offset_x = int(window.winfo_rootx() * scale)
    offset_y = int(window.winfo_rooty() * scale)
    width = int(window.winfo_width() * scale)
    height = int(window.winfo_height() * scale)
    _grab_with_windows(offset_x, offset_y, width, height, target)
    window.attributes("-topmost", False)


def _dpi_scale(window: MainWindow) -> float:
    """逻辑单位 → 物理像素的系数（96 DPI 时为 1.0）。"""
    return float(window.tk.call("tk", "scaling")) / (96 / 72)


def _grab_with_windows(x: int, y: int, width: int, height: int, target: Path) -> None:
    """用 PowerShell + System.Drawing 抓一块屏幕区域存成 PNG。"""
    script = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$bmp = New-Object System.Drawing.Bitmap({width}, {height}); "
        "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        f"$g.CopyFromScreen({x}, {y}, 0, 0, $bmp.Size); "
        f"$bmp.Save('{target}', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$g.Dispose(); $bmp.Dispose()"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0 or not target.exists():
        raise RuntimeError(f"抓屏失败：{completed.stderr.strip()[:200]}")


def run(out_dir: Path, keep: bool) -> int:
    """跑完整流程；返回 0 表示 10 张全生成。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui-shots-", ignore_cleanup_errors=True) as raw:
        db_path = build_database(Path(raw))
        conn = connect(db_path)
        window = MainWindow(Session(conn=conn))
        produced = 0
        try:
            # 逻辑尺寸按 DPI 折算，保证物理窗口 ≈ 1380×840，正好落在 1707×1067 屏内。
            scale = _dpi_scale(window)
            window.geometry(f"{int(1640 / scale)}x{int(960 / scale)}+10+10")
            window.deiconify()
            window.update()
            _login(window, CUSTOMER_LOGIN)
            _prepare_context(window)
            for key, filename in SHOTS:
                if key in {"inventory", "hotel_console"}:
                    _login(window, STAFF_LOGIN)
                elif key in {"admin", "audit", "reconcile", "reports"}:
                    _login(window, ADMIN_LOGIN)
                elif key in {"search", "results", "my_orders", "login"}:
                    if key != "login":
                        _login(window, CUSTOMER_LOGIN)
                if key == "login":
                    window.show("login")
                else:
                    window.show(key)
                _trigger(window, key)
                if key in {"my_orders", "results", "hotel_console", "inventory"}:
                    _select_first(window, key)
                capture(window, out_dir / f"{filename}.png")
                produced += 1
                print(f"shot={filename}.png screen={key} ok=True")
        finally:
            window.destroy()
            conn.close()
        print(f"shots={produced} out={out_dir}")
        if keep:
            print(f"db={db_path}")
            input("按回车结束……")
    return 0 if produced == len(SHOTS) else 1


def _login(window: MainWindow, login_name: str) -> None:
    """切身份并重建导航；未登录时 ``login`` 会抛错，这里直接吞掉。"""
    try:
        window.session.login(login_name, PASSWORD)
    except Exception:  # pylint: disable=broad-exception-caught
        print(f"login_failed={login_name}")
        return
    window.refresh_nav()


def _prepare_context(window: MainWindow) -> None:
    """给搜索页与结果页塞一组条件；从后天起，落在种子的 90 天窗口内。"""
    start = date.today() + timedelta(days=2)
    window.session.remember(
        keyword="",
        check_in=start.isoformat(),
        check_out=(start + timedelta(days=2)).isoformat(),
    )


def _select_first(window: MainWindow, key: str) -> None:
    """把表格第一行选中并触发详情，截图才看得出「选中后右侧/下方有内容」。"""
    # 截图脚本就是要在不点界面的情况下驱动屏幕，这里访问私有映射是有意的。
    screen = window._screens[key]  # pylint: disable=protected-access
    tree = getattr(screen, "tree", None)
    if tree is None:
        return
    children = tree.get_children()
    if not children:
        return
    tree.selection_set(children[0])
    tree.focus(children[0])
    tree.event_generate("<<TreeviewSelect>>")
    window.update()


def _trigger(window: MainWindow, key: str) -> None:
    """有些屏只有点按钮才有内容，截图前替用户点一下。"""
    screen = window._screens.get(key)  # pylint: disable=protected-access
    if screen is None:
        return
    if key == "reconcile" and hasattr(screen, "run_check"):
        screen.run_check()
    elif key == "reports" and hasattr(screen, "run_report"):
        screen.run_report()


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="生成 10 屏截图（S6-2）")
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "docs" / "screenshots"),
        help="输出目录，默认 exp3/docs/screenshots",
    )
    parser.add_argument("--keep", action="store_true", help="保留临时库并等待回车")
    args = parser.parse_args(argv)
    return run(Path(args.out), args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
