"""测试公共设施：路径引导、临时库、最小夹具。

两种跑法都必须成立（S1-5/6/7 用第一种，S2-1 的 discover 用第二种）：

- ``python -m unittest code.tests.test_tx -v``（cwd = ``exp3/``，``code`` 是命名空间包）
- ``python -m unittest discover -s code/tests -t code -v``（``code/`` 进 sys.path）

因此这里显式把 ``code/`` 插到 ``sys.path``，测试内部统一 ``from app... import``。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.infrastructure.db import connection as db_connection  # noqa: E402
from app.infrastructure.db import migrate_runner  # noqa: E402


@contextmanager
def temp_database(with_seed: bool = False) -> Iterator[tuple[object, Path]]:
    """在临时目录建一个已迁移的库，退出时删目录。

    Args:
        with_seed: 是否顺带写入 720 行的完整种子（默认 False，用最小夹具更快）。

    Yields:
        ``(connection, db_path)``。
    """
    workspace = Path(tempfile.mkdtemp(prefix="exp3-test-"))
    path = workspace / "test.db"
    conn = db_connection.connect(path)
    try:
        migrate_runner.apply_migrations(conn)
        if with_seed:
            # 局部导入：seed 会反向依赖 connection，顶层导入在"仅建表"路径上属于额外耦合。
            from app.infrastructure.db import seed as seed_module  # pylint: disable=import-outside-toplevel

            seed_module.seed_all(conn, {})
        yield conn, path
    finally:
        conn.close()
        shutil.rmtree(workspace, ignore_errors=True)


def insert_fixture(conn) -> dict[str, int]:  # noqa: ANN001 - sqlite3.Connection，避免测试层依赖类型
    """插入一套最小夹具：1 家酒店、1 个房型（总房量 5）、1 个顾客、1 名店长。

    Returns:
        主键字典：``hotel_id`` / ``room_type_id`` / ``guest_id`` / ``staff_id``。
    """
    stamp = "2026-11-25 00:00:00"
    hotel_id = int(
        conn.execute(
            "INSERT INTO hotel (name, address, phone, description, audit_status,"
            " created_at, audited_at) VALUES ('测试酒店', '测试路 1 号', '010-00000000',"
            " '夹具', 'APPROVED', ?, ?)",
            (stamp, stamp),
        ).lastrowid
    )
    room_type_id = int(
        conn.execute(
            "INSERT INTO room_type (hotel_id, name, bed_type, area_sqm, capacity, total_rooms)"
            " VALUES (?, '测试大床房', '大床 1.8m', 30, 2, 5)",
            (hotel_id,),
        ).lastrowid
    )
    guest_id = int(
        conn.execute(
            "INSERT INTO user_account (login_name, password_hash, role, hotel_id, status,"
            " created_at) VALUES ('13900000001', 'x', 'CUSTOMER', NULL, 'ACTIVE', ?)",
            (stamp,),
        ).lastrowid
    )
    staff_id = int(
        conn.execute(
            "INSERT INTO user_account (login_name, password_hash, role, hotel_id, status,"
            " created_at) VALUES ('13900000002', 'x', 'HOTEL_STAFF', ?, 'ACTIVE', ?)",
            (hotel_id, stamp),
        ).lastrowid
    )
    return {
        "hotel_id": hotel_id,
        "room_type_id": room_type_id,
        "guest_id": guest_id,
        "staff_id": staff_id,
    }


def insert_inventory(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    conn,  # noqa: ANN001
    room_type_id: int,
    stay_date: str,
    available: int,
    occupied: int = 0,
    sale_status: str = "ON_SALE",
) -> None:
    """写一行每日库存（价格表同步写一行，避免报表查询缺价）。

    参数直接镜像 ``room_inventory`` 的列，测试里按列名逐个显式传值最直观，
    因此这里接受 6 个位置参数。
    """
    stamp = "2026-11-25 00:00:00"
    conn.execute(
        "INSERT INTO room_inventory (room_type_id, stay_date, available_rooms,"
        " occupied_rooms, sale_status, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (room_type_id, stay_date, available, occupied, sale_status, stamp),
    )
    conn.execute(
        "INSERT INTO room_price (room_type_id, stay_date, unit_price_cents, updated_at)"
        " VALUES (?, ?, 30000, ?)",
        (room_type_id, stay_date, stamp),
    )


def insert_booking(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    conn,  # noqa: ANN001
    fixture: dict[str, int],
    booking_no: str,
    check_in: str,
    check_out: str,
    status: str = "PENDING",
) -> int:
    """写一张订单（不写逐晚快照，约束用例不需要）。

    同理镜像 ``booking`` 的关键列，便于用例只写关心的字段、其余走默认值。
    """
    stamp = "2026-11-25 00:00:00"
    cursor = conn.execute(
        "INSERT INTO booking (booking_no, guest_id, hotel_id, room_type_id, room_count,"
        " check_in_date, check_out_date, total_price_cents, status, idempotency_key,"
        " cancel_reason, cancel_initiator, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, 1, ?, ?, 30000, ?, NULL, NULL, NULL, ?, ?)",
        (
            booking_no,
            fixture["guest_id"],
            fixture["hotel_id"],
            fixture["room_type_id"],
            check_in,
            check_out,
            status,
            stamp,
            stamp,
        ),
    )
    return int(cursor.lastrowid)
