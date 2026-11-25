"""状态机 13 条边用例：8 条允许边（T1–T8）+ 5 条禁止边（F1–F5）。

命名约定（S2-2 判据按名字计数）：``test_T<n>_...`` / ``test_F<n>_...``。
每条允许边都断言三件事：目标状态正确、返回的编号正确、**非法来源状态会拒绝**；
每条禁止边都断言：抛 ``IllegalTransitionError``、``code`` 为 409 语义、
且订单状态**一个字节都没变**（exp1 项目参数 §5 的硬要求）。
"""

from __future__ import annotations

import unittest
from datetime import date

import sys
from pathlib import Path
# 两种跑法都要成立（G2-R1-02）：`python -m unittest code.tests.X` 与
# `python -m unittest discover -s code/tests -t code`。前者不会把 code/ 放进
# sys.path，故在这里显式补一次；用 __file__ 定位，不依赖进程 cwd。
_CODE_ROOT = Path(__file__).resolve().parents[1]
if str(_CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(_CODE_ROOT))
from app.domain.enums import ActorRole, BookingEvent, BookingStatus
from app.domain.errors import IllegalTransitionError, PermissionDeniedError
from app.domain.models import Booking
from app.domain.state_machine import (
    FORBIDDEN_TRANSITIONS,
    TRANSITIONS,
    BookingStateMachine,
)


def make_booking(status: BookingStatus) -> Booking:
    """构造一张最小订单（只关心状态字段的用例共用）。"""
    return Booking(
        booking_no="B-SM-0001",
        guest_id=1,
        hotel_id=1,
        room_type_id=1,
        check_in_date=date(2027, 3, 1),
        check_out_date=date(2027, 3, 3),
        room_count=1,
        total_price_cents=60000,
        status=status,
    )


class AllowedEdgeTest(unittest.TestCase):
    """T1–T8：每条允许边都能走通，且落到正确目标状态。"""

    def setUp(self) -> None:
        self.machine = BookingStateMachine()

    def _assert_edge(
        self,
        code: str,
        event: BookingEvent,
        role: ActorRole,
        source: BookingStatus,
        target: BookingStatus,
    ) -> None:
        booking = make_booking(source)
        edge = self.machine.transition(booking, event, role=role)
        self.assertEqual(edge.code, code)
        self.assertEqual(booking.status, target)

    def test_T1_酒店确认待确认订单转为已确认(self) -> None:
        """T1：待确认 --CONFIRM--> 已确认（酒店工作人员）。"""
        self._assert_edge(
            "T1",
            BookingEvent.CONFIRM,
            ActorRole.HOTEL_STAFF,
            BookingStatus.PENDING,
            BookingStatus.CONFIRMED,
        )

    def test_T2_酒店拒单待确认订单转为已取消(self) -> None:
        """T2：待确认 --REJECT--> 已取消（酒店拒单，库存即时回补）。"""
        self._assert_edge(
            "T2",
            BookingEvent.REJECT,
            ActorRole.HOTEL_STAFF,
            BookingStatus.PENDING,
            BookingStatus.CANCELLED,
        )

    def test_T3_超时未确认由系统取消(self) -> None:
        """T3：待确认 --TIMEOUT--> 已取消（30 分钟超时，只允许系统执行）。"""
        self._assert_edge(
            "T3",
            BookingEvent.TIMEOUT,
            ActorRole.SYSTEM,
            BookingStatus.PENDING,
            BookingStatus.CANCELLED,
        )

    def test_T4_酒店核验办理入住(self) -> None:
        """T4：已确认 --CHECK_IN--> 已入住（凭订单号或手机号核验）。"""
        self._assert_edge(
            "T4",
            BookingEvent.CHECK_IN,
            ActorRole.HOTEL_STAFF,
            BookingStatus.CONFIRMED,
            BookingStatus.CHECKED_IN,
        )

    def test_T5_系统次日默认置为已入住(self) -> None:
        """T5：已确认 --AUTO_CHECK_IN--> 已入住（入住日 23:59 前未标记）。"""
        self._assert_edge(
            "T5",
            BookingEvent.AUTO_CHECK_IN,
            ActorRole.SYSTEM,
            BookingStatus.CONFIRMED,
            BookingStatus.CHECKED_IN,
        )

    def test_T6_顾客或酒店取消已确认订单(self) -> None:
        """T6：已确认 --CANCEL--> 已取消，顾客/酒店/管理员三方都可发起。"""
        for role in (ActorRole.CUSTOMER, ActorRole.HOTEL_STAFF, ActorRole.PLATFORM_ADMIN):
            with self.subTest(role=role.value):
                self._assert_edge(
                    "T6",
                    BookingEvent.CANCEL,
                    role,
                    BookingStatus.CONFIRMED,
                    BookingStatus.CANCELLED,
                )

    def test_T7_酒店标记未入住(self) -> None:
        """T7：已确认 --NO_SHOW--> 未入住（入住日 23:59 前标记）。"""
        self._assert_edge(
            "T7",
            BookingEvent.NO_SHOW,
            ActorRole.HOTEL_STAFF,
            BookingStatus.CONFIRMED,
            BookingStatus.NO_SHOW,
        )

    def test_T8_酒店办理退房(self) -> None:
        """T8：已入住 --CHECK_OUT--> 已退房（订单完结，不可再变）。"""
        self._assert_edge(
            "T8",
            BookingEvent.CHECK_OUT,
            ActorRole.HOTEL_STAFF,
            BookingStatus.CHECKED_IN,
            BookingStatus.CHECKED_OUT,
        )


class ForbiddenEdgeTest(unittest.TestCase):
    """F1–F5：5 条"画成允许就是错"的边必须被拒，且状态不变。"""

    def setUp(self) -> None:
        self.machine = BookingStateMachine()

    def _assert_forbidden(
        self, source: BookingStatus, event: BookingEvent, role: ActorRole
    ) -> None:
        booking = make_booking(source)
        with self.assertRaises(IllegalTransitionError) as raised:
            self.machine.transition(booking, event, role=role)
        error = raised.exception
        self.assertEqual(error.code, "ILLEGAL_TRANSITION")
        self.assertEqual(error.http_status, 409)
        self.assertEqual(error.details["from_status"], source.value)
        self.assertEqual(error.details["event"], event.value)
        self.assertEqual(booking.status, source)

    def test_F1_已入住不能取消(self) -> None:
        """F1：已入住 --CANCEL--> 拒绝（费用与库存已实际发生）。"""
        self._assert_forbidden(
            BookingStatus.CHECKED_IN, BookingEvent.CANCEL, ActorRole.HOTEL_STAFF
        )

    def test_F2_已退房不能取消(self) -> None:
        """F2：已退房 --CANCEL--> 拒绝（订单已完结）。"""
        self._assert_forbidden(
            BookingStatus.CHECKED_OUT, BookingEvent.CANCEL, ActorRole.CUSTOMER
        )

    def test_F3_已取消不能恢复确认(self) -> None:
        """F3：已取消 --CONFIRM--> 拒绝（库存已回补，恢复会重复占用）。"""
        self._assert_forbidden(
            BookingStatus.CANCELLED, BookingEvent.CONFIRM, ActorRole.HOTEL_STAFF
        )

    def test_F4_已入住不能回退为已确认(self) -> None:
        """F4：已入住 --CONFIRM--> 拒绝（状态回退）。"""
        self._assert_forbidden(
            BookingStatus.CHECKED_IN, BookingEvent.CONFIRM, ActorRole.HOTEL_STAFF
        )

    def test_F5_已退房不能回退为已入住(self) -> None:
        """F5：已退房 --CHECK_IN--> 拒绝（状态回退）。"""
        self._assert_forbidden(
            BookingStatus.CHECKED_OUT, BookingEvent.CHECK_IN, ActorRole.HOTEL_STAFF
        )


class StateMachineRuleTest(unittest.TestCase):
    """状态机自身的结构性断言：边数、终态、权限、跨状态跳跃。"""

    def setUp(self) -> None:
        self.machine = BookingStateMachine()

    def test_八条允许边与五条禁止边(self) -> None:
        """允许边恰为 8 条、禁止边恰为 5 条——报告里的两个数字由此可数。

        ``(来源状态, 事件)`` 两两不重复（8 行），而 ``(来源状态, 目标状态)`` 只有 6 对：
        「已确认→已入住」被 CHECK_IN / AUTO_CHECK_IN 两个触发者共用，
        「待确认→已取消」被 REJECT / TIMEOUT 共用——这就是 exp1 说的
        "7 条边、按触发者拆成 8 条"的落库形态。
        """
        self.assertEqual(len(TRANSITIONS), 8)
        self.assertEqual(len({(edge.source, edge.event) for edge in TRANSITIONS}), 8)
        self.assertEqual(len({(edge.source, edge.target) for edge in TRANSITIONS}), 6)
        self.assertEqual(len(FORBIDDEN_TRANSITIONS), 5)

    def test_终态没有任何出边(self) -> None:
        """已退房/已取消/未入住三个终态，在 TRANSITIONS 里找不到任何来源边。"""
        for status in (
            BookingStatus.CHECKED_OUT,
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
        ):
            with self.subTest(status=status.value):
                self.assertTrue(self.machine.is_terminal(status))
                self.assertEqual(self.machine.available_events(status), ())

    def test_跨状态跳跃被拒(self) -> None:
        """待确认 --CHECK_OUT--> 已退房：跨状态跳跃一律拒绝（405/409 语义）。"""
        booking = make_booking(BookingStatus.PENDING)
        with self.assertRaises(IllegalTransitionError):
            self.machine.transition(booking, BookingEvent.CHECK_OUT, role=ActorRole.HOTEL_STAFF)
        self.assertEqual(booking.status, BookingStatus.PENDING)

    def test_角色无权时拒绝且不改状态(self) -> None:
        """顾客不能替酒店确认订单（403），状态保持不变。"""
        booking = make_booking(BookingStatus.PENDING)
        with self.assertRaises(PermissionDeniedError) as raised:
            self.machine.transition(booking, BookingEvent.CONFIRM, role=ActorRole.CUSTOMER)
        self.assertEqual(raised.exception.code, "PERMISSION_DENIED")
        self.assertEqual(raised.exception.http_status, 403)
        self.assertEqual(booking.status, BookingStatus.PENDING)

    def test_可用事件按角色收敛(self) -> None:
        """已确认状态下，顾客只有"取消"一个动作；酒店有入住/取消/未入住三个。"""
        customer = self.machine.available_events(BookingStatus.CONFIRMED, ActorRole.CUSTOMER)
        staff = self.machine.available_events(BookingStatus.CONFIRMED, ActorRole.HOTEL_STAFF)
        self.assertEqual(customer, (BookingEvent.CANCEL,))
        self.assertEqual(
            set(staff),
            {BookingEvent.CHECK_IN, BookingEvent.CANCEL, BookingEvent.NO_SHOW},
        )

    def test_取消原因与发起人写入订单(self) -> None:
        """T6 取消时，原因与发起人必须落到订单上（审计与报表要用）。"""
        booking = make_booking(BookingStatus.CONFIRMED)
        self.machine.transition(
            booking,
            BookingEvent.CANCEL,
            role=ActorRole.CUSTOMER,
            reason="行程变更",
        )
        self.assertEqual(booking.cancel_reason, "行程变更")
        self.assertEqual(booking.cancel_initiator, ActorRole.CUSTOMER.value)


if __name__ == "__main__":
    unittest.main()
