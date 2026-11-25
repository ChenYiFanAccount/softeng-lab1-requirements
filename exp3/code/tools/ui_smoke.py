"""界面冒烟：逐屏构造再销毁，确认 10 个屏都能起来（S6-1）。

为什么单独做成命令行工具而不是 unittest：屏幕构造要与真实 Tk 主窗口交互，
``python -m unittest`` 里默认没有 ``mainloop``，一旦某屏真的进了事件循环就会卡住；
这里显式 ``update()`` 一次再 ``destroy()``，跑完即退，适合放证据里。

退出码：10 屏全部构造成功 → 0；任一屏抛异常 → 1。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.infrastructure.db.connection import connect, load_settings  # noqa: E402
from app.infrastructure.db.migrate_runner import apply_migrations  # noqa: E402
from app.infrastructure.db.seed import seed_all  # noqa: E402
from app.ui.app import SCREENS, SCREEN_NAMES, MainWindow  # noqa: E402
from app.ui.session import Session  # noqa: E402


def build_database(base_dir: Path) -> Path:
    """在临时目录里建一份带种子的库，冒烟不碰开发库。"""
    db_path = base_dir / "ui_smoke.db"
    conn = connect(db_path)
    try:
        apply_migrations(conn)
        seed_all(conn, load_settings())
    finally:
        conn.close()
    return db_path


def smoke(db_path: Path) -> int:
    """逐屏构造；返回失败屏数。"""
    conn = connect(db_path)
    window = MainWindow(Session(conn=conn))
    failures = 0
    print(f"screen_count_expected={len(SCREENS)}")
    try:
        for index, spec in enumerate(SCREENS, start=1):
            try:
                window.show(spec.key)
                window.update_idletasks()
                window.update()
                print(f"screen[{index:02d}] key={spec.key} name={spec.label} ok=True")
            except Exception:  # pylint: disable=broad-exception-caught
                failures += 1
                print(f"screen[{index:02d}] key={spec.key} name={spec.label} ok=False")
                traceback.print_exc(limit=3)
        print("screen_names=" + " | ".join(SCREEN_NAMES))
    finally:
        window.destroy()
        conn.close()
    print(f"screen_total={len(SCREENS)} failures={failures}")
    print(f"check={'passed' if failures == 0 else 'failed'}")
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    """命令行入口：``--keep`` 保留临时库便于人工看数据。"""
    parser = argparse.ArgumentParser(description="逐屏构造冒烟（S6-1）")
    parser.add_argument("--keep", action="store_true", help="保留临时数据库")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(
        prefix="ui-smoke-", ignore_cleanup_errors=True
    ) as raw_dir:
        base_dir = Path(raw_dir)
        db_path = build_database(base_dir)
        code = smoke(db_path)
        if args.keep:
            print(f"db={db_path}")
            input("按回车结束，临时目录会一并删除……")
        return code


if __name__ == "__main__":
    raise SystemExit(main())
