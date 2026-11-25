"""生成 10 张界面截图，供 S6-2 交付与报告引用。

做法：在临时库里铺一套"什么状态都有"的演示数据（待确认 / 已确认 / 已入住 /
已退房 / 已取消 / 未入住），再开真窗口逐屏 ``show`` + ``update``，用
``PrintWindow`` 把窗口整体渲染成位图，存到 ``--out`` 指定目录（默认
``docs/screenshots/``）。

判据口径（S6-R1-01）：抓完逐张自检——PNG 宽高必须等于 ``GetWindowRect``
的宽高，且每屏表格的列宽合计不得超过 Treeview 可视宽度；任一不满足即
抛错退出（退出码非 0），不会留下"看起来截成功"的残图。

为什么不手点：10 屏 × 每种状态都要有数据，手点一次要十几分钟且不可复现；
脚本跑一次十几秒，报告里的图与库里的数据能对上。

用法：
    python code/tools/take_screenshots.py --out %TEMP%/shots   # 先出到临时目录复验
    python code/tools/take_screenshots.py                      # 复验通过后再覆盖仓库
"""

from __future__ import annotations

import argparse
import ctypes
import struct
import sys
import tempfile
import tkinter as tk
import zlib
from datetime import date, timedelta
from pathlib import Path

def enable_dpi_awareness() -> None:
    """让进程按物理像素工作（Per-Monitor V2）。

    Windows 上 Tk 默认不是 DPI 感知的：150% 缩放下 `geometry("1640x960")`
    会被系统再放大 1.5 倍，窗口超出屏幕、右侧被裁——S6-R1-01 的根因。
    设成 DPI 感知后，Tk 的坐标与屏幕像素一一对应，`PrintWindow` 抓到的
    位图也就是窗口本身。
    """
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


def capture(window: MainWindow, target: Path, key: str = "") -> tuple[int, int]:
    """截主窗口；用 ``PrintWindow`` 抓整窗，尺寸与 ``GetWindowRect`` 自校验。

    为什么不用 ``CopyFromScreen``：那是按屏幕坐标取像，进程若不是 DPI 感知
    （本机 150% 缩放），Tk 报的逻辑尺寸乘出来的物理矩形会小于真实窗口，
    右边一列就会被截在画面外（S6-R1-01）。``PrintWindow`` 由系统把整窗
    渲染到位图，宽高直接取自 ``GetWindowRect``，与缩放比例无关。
    """
    window.update_idletasks()
    # 抓屏要窗口在前台：PrintWindow 对最小化窗口不可靠，且用户可能切走。
    window.attributes("-topmost", True)
    window.lift()
    window.focus_force()
    window.update()
    _settle(window, 350)
    window.update()

    width, height = _grab_with_printwindow(window, target)
    _check_capture(window, target, width, height, key)
    window.attributes("-topmost", False)
    return width, height


def _settle(window: MainWindow, milliseconds: int) -> None:
    """等窗口把重绘做完，但**不睡线程**（S6-R1-02 要求全仓无 ``sleep``）。"""
    done = tk.BooleanVar(master=window, value=False)
    window.after(milliseconds, lambda: done.set(True))
    window.wait_variable(done)


class _Rect(ctypes.Structure):  # pylint: disable=too-few-public-methods
    """Win32 ``RECT``。"""

    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _BitmapInfoHeader(ctypes.Structure):  # pylint: disable=too-few-public-methods
    """Win32 ``BITMAPINFOHEADER``。"""

    _fields_ = [
        ("size", ctypes.c_uint32),
        ("width", ctypes.c_long),
        ("height", ctypes.c_long),
        ("planes", ctypes.c_uint16),
        ("bit_count", ctypes.c_uint16),
        ("compression", ctypes.c_uint32),
        ("size_image", ctypes.c_uint32),
        ("x_pels", ctypes.c_long),
        ("y_pels", ctypes.c_long),
        ("clr_used", ctypes.c_uint32),
        ("clr_important", ctypes.c_uint32),
    ]


class _BitmapInfo(ctypes.Structure):  # pylint: disable=too-few-public-methods
    """Win32 ``BITMAPINFO``（只用到 RGB 三色掩码位）。"""

    _fields_ = [("header", _BitmapInfoHeader), ("colors", ctypes.c_uint32 * 3)]


def _grab_with_printwindow(window: MainWindow, target: Path) -> tuple[int, int]:
    """用 ``PrintWindow`` 把整窗渲染进 DIB，再手写 PNG；返回位图宽高。

    全程只用 ``ctypes`` 调 ``user32``/``gdi32``：既不需要 Pillow，也不需要
    起 PowerShell（``Add-Type`` 在某些受限目录下会因临时文件被拒而失败）。
    """
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    gdi32 = ctypes.windll.gdi32  # type: ignore[attr-defined]

    hwnd = user32.GetAncestor(int(window.winfo_id()), 2)  # GA_ROOT=2，取带边框的顶层窗
    rect = _Rect()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetWindowRect 失败")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError(f"窗口矩形为空：{width}x{height}")

    screen_dc = user32.GetDC(0)
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    info = _BitmapInfo()
    info.header.size = ctypes.sizeof(_BitmapInfoHeader)
    info.header.width = width
    info.header.height = -height  # 负高度 = 自上而下
    info.header.planes = 1
    info.header.bit_count = 32
    info.header.compression = 0
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(
        memory_dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0
    )
    gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 2):  # PW_RENDERFULLCONTENT
            raise RuntimeError("PrintWindow 失败")
        buffer = ctypes.string_at(bits, width * height * 4)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(0, screen_dc)

    _write_png(target, width, height, buffer)
    return width, height


def _write_png(path: Path, width: int, height: int, bgra: bytes) -> None:
    """把 32 位 BGRA（自上而下）写成真彩色 PNG，只用 ``zlib`` + ``struct``。"""
    rows: list[bytes] = []
    stride = width * 4
    for row_index in range(height):
        row = bgra[row_index * stride : (row_index + 1) * stride]
        rgb = bytearray(width * 3)
        rgb[0::3] = row[2::4]
        rgb[1::3] = row[1::4]
        rgb[2::3] = row[0::4]
        rows.append(b"\x00" + bytes(rgb))  # filter type 0
    compressed = zlib.compress(b"".join(rows), 6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def _check_capture(
    window: MainWindow, target: Path, width: int, height: int, key: str
) -> tuple[int, int]:
    """自检：PNG 实际宽高 == ``GetWindowRect``，且表格末列右界落在窗口内。"""
    header = target.read_bytes()[16:24]
    png_width = int.from_bytes(header[0:4], "big")
    png_height = int.from_bytes(header[4:8], "big")
    if (png_width, png_height) != (width, height):
        raise RuntimeError(
            f"尺寸不一致：GetWindowRect={width}x{height} png={png_width}x{png_height}"
        )

    logical_width = window.winfo_width()
    if logical_width > 0 and png_width < logical_width:
        raise RuntimeError(
            f"抓到的图比窗口还窄：png={png_width} 逻辑宽={logical_width}"
        )

    if key:
        screen = window._screens.get(key)  # pylint: disable=protected-access
        tree = getattr(screen, "tree", None) if screen is not None else None
        if tree is not None:
            columns = tree["columns"]
            total = sum(int(tree.column(name, "width")) for name in columns)
            visible = int(tree.winfo_width())
            if 1 < visible < total:
                raise RuntimeError(
                    f"{key} 表格列宽合计 {total} 超出可视宽 {visible}，末列会被裁掉"
                )
    return png_width, png_height

def run(out_dir: Path, keep: bool) -> int:
    """跑完整流程；返回 0 表示 10 张全生成。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui-shots-", ignore_cleanup_errors=True) as raw:
        db_path = build_database(Path(raw))
        conn = connect(db_path)
        window = MainWindow(Session(conn=conn))
        produced = 0
        try:
            # 进程已 DPI 感知，这里的 1640×960 就是物理像素，落在 1707×1067 屏内。
            window.geometry("1640x960+10+10")
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
                width, height = capture(window, out_dir / f"{filename}.png", key)
                produced += 1
                print(f"shot={filename}.png screen={key} size={width}x{height} ok=True")
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
