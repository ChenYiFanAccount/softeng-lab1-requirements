"""S4-4：审计只追加，失败（403 / 409）也要留痕。

三条口径：

1. **只追加**：代码里没有删除或更新审计的语句（判据是仓库级 grep，本文件只
   从数据侧佐证——同一笔操作前后，旧记录一条不少）。
2. **失败也是事实**：被规则拒的流转（409）与被权限拒的流转（403）都要落一行，
   ``action`` 前缀分别是 ``REJECTED:`` 与 ``DENIED:``，``before_state`` 与
   ``after_state`` 相同（状态确实没变）。
3. **同事务**：失败审计与"订单状态未变"在同一个事务里提交，不会出现"审计记了
   一次拒绝、订单却也变了"的错位。
"""

from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:  # 两种跑法都要成立（G2-R1-02）
    sys.path.insert(0, str(_CODE_ROOT))

try:  # 两种跑法：`-m unittest code.tests.x` 与 `discover -s code/tests -t code`
    from code.tests import support
except ImportError:  # pragma: no cover - discover 模式
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import FrozenClock
from app.application.commands import PlaceBookingCommand
from app.domain.enums import ActorRole, BookingEvent, BookingStatus
from app.domain.errors import IllegalTransitionError, PermissionDeniedError

#: 住宿日期
CHECK_IN = "2027-03-01"
CHECK_OUT = "2027-03-03"

#: 建单时刻
CREATED_AT = datetime(2026, 11, 25, 9, 0, 0)


class AuditAppendOnlyTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """审计表的行为契约：只增、失败必留痕、状态与记录同事务。"""

    def setUp(self) -> None:
        self._stack = ExitStack()
        self.conn, self.path = self._stack.enter_context(support.temp_database())
        self.fix = support.insert_fixture(self.conn)
        for day in ("2027-03-01", "2027-03-02"):
            support.insert_inventory(self.conn, self.fix["room_type_id"], day, 5)
        self.clock = FrozenClock(CREATED_AT)
        self.service = BookingAppService(self.conn, clock=self.clock)
        self.guest = Actor(self.fix["guest_id"], ActorRole.CUSTOMER, login_name="13900000001")
        self.staff = Actor(
            self.fix["staff_id"],
            ActorRole.HOTEL_STAFF,
            hotel_id=self.fix["hotel_id"],
            login_name="13900000002",
        )

    def tearDown(self) -> None:
        self._stack.close()

    # ---------------------------------------------------------------- 工具

    def place(self) -> str:
        """下一张待确认单，返回订单号。"""
        booking = self.service.place_booking(
            PlaceBookingCommand(
                guest_id=self.fix["guest_id"],
                hotel_id=self.fix["hotel_id"],
                room_type_id=self.fix["room_type_id"],
                check_in_date=datetime.strptime(CHECK_IN, "%Y-%m-%d").date(),
                check_out_date=datetime.strptime(CHECK_OUT, "%Y-%m-%d").date(),
                room_count=1,
            ),
            self.guest,
        )
        return booking.booking_no

    def rows(self) -> list[tuple[str, str, str, str]]:
        """审计行（新→旧）：action / before / after / operator_role。"""
        cursor = self.conn.execute(
            "SELECT action, before_state, after_state, operator_role "
            "FROM audit_log ORDER BY id DESC"
        )
        return [
            (
                str(row["action"]),
                str(row["before_state"]),
                str(row["after_state"]),
                str(row["operator_role"]),
            )
            for row in cursor.fetchall()
        ]

    def count(self) -> int:
        """审计总行数。"""
        return int(self.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])

    # ---------------------------------------------------------------- 用例

    def test_409被规则拒时留一条REJECTED审计(self) -> None:
        booking_no = self.place()
        self.service.apply_event(booking_no, BookingEvent.REJECT, self.staff)
        before = self.count()

        with self.assertRaises(IllegalTransitionError):
            self.service.apply_event(booking_no, BookingEvent.CANCEL, self.staff)

        self.assertEqual(self.count(), before + 1)
        action, before_state, after_state, role = self.rows()[0]
        self.assertEqual(action, "REJECTED:CANCEL")
        self.assertEqual(before_state, "CANCELLED")
        self.assertEqual(after_state, "CANCELLED")
        self.assertEqual(role, "HOTEL")

    def test_403越权时留一条DENIED审计(self) -> None:
        booking_no = self.place()
        before = self.count()

        with self.assertRaises(PermissionDeniedError):
            self.service.apply_event(booking_no, BookingEvent.CONFIRM, self.guest)

        self.assertEqual(self.count(), before + 1)
        action, before_state, after_state, role = self.rows()[0]
        self.assertEqual(action, "DENIED:CONFIRM")
        self.assertEqual(before_state, "PENDING")
        self.assertEqual(after_state, "PENDING")
        self.assertEqual(role, "CUSTOMER")

    def test_失败审计不改变订单状态(self) -> None:
        booking_no = self.place()

        with self.assertRaises(PermissionDeniedError):
            self.service.apply_event(booking_no, BookingEvent.CONFIRM, self.guest)

        reloaded = self.service.get_booking(booking_no, self.guest)
        self.assertIs(reloaded.status, BookingStatus.PENDING)

    def test_整条链路只增不减(self) -> None:
        booking_no = self.place()
        seen = [self.count()]
        for event, actor in (
            (BookingEvent.CONFIRM, self.staff),
            (BookingEvent.CHECK_IN, self.staff),
            (BookingEvent.CHECK_OUT, self.staff),
        ):
            self.service.apply_event(booking_no, event, actor)
            seen.append(self.count())

        self.assertEqual(seen, sorted(seen))
        self.assertEqual(len(set(seen)), len(seen))
        actions = [row[0] for row in reversed(self.rows())]
        self.assertEqual(actions, ["CREATE", "CONFIRM", "CHECK_IN", "CHECK_OUT"])

    def test_失败审计里的操作者角色可追溯(self) -> None:
        booking_no = self.place()
        with self.assertRaises(PermissionDeniedError):
            self.service.apply_event(booking_no, BookingEvent.CONFIRM, self.guest)

        row = self.conn.execute(
            "SELECT operator_id, operator_role, target_type, target_id, action "
            "FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(int(row["operator_id"]), self.fix["guest_id"])
        self.assertEqual(str(row["operator_role"]), "CUSTOMER")
        self.assertEqual(str(row["target_type"]), "BOOKING")
        self.assertEqual(str(row["target_id"]), booking_no)
        self.assertEqual(str(row["action"]), "DENIED:CONFIRM")


if __name__ == "__main__":
    unittest.main()
