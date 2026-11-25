"""库存维护用例（M2）：调可售、停售、复售与三条校验。

这三条校验容易被漏掉，但每一条漏掉都会写出坏数据：
①非本酒店员工不能改；②可售不能小于已占用（否则等于抹掉已卖出的房）；
③可售不能超过房型总房量（否则余量算出负数级别的怪结果）。
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from datetime import datetime

try:  # 两种跑法见 support.py
    from code.tests import support
except ImportError:  # pragma: no cover - discover 模式
    import support  # type: ignore[no-redef]

# pylint: disable=missing-function-docstring
# 用例名即命题，docstring 只会重复方法名。

from app.application.actor import Actor
from app.application.clock import FrozenClock
from app.application.inventory_service import InventoryAppService
from app.domain.enums import ActorRole
from app.domain.errors import PermissionDeniedError, ValidationError


class InventoryAdminTest(unittest.TestCase):  # pylint: disable=too-many-instance-attributes
    """酒店员工维护本店库存。"""

    def setUp(self) -> None:
        self._stack = ExitStack()
        self.conn, self.path = self._stack.enter_context(support.temp_database())
        self.fix = support.insert_fixture(self.conn)
        support.insert_inventory(self.conn, self.fix["room_type_id"], "2027-03-01", 5, occupied=2)
        support.insert_inventory(self.conn, self.fix["room_type_id"], "2027-03-02", 5)
        clock = FrozenClock(datetime(2026, 11, 25, 13, 0))
        self.service = InventoryAppService(self.conn, clock=clock)
        self.staff = Actor(
            self.fix["staff_id"], ActorRole.HOTEL_STAFF, hotel_id=self.fix["hotel_id"]
        )
        self.admin = Actor(self.fix["staff_id"] + 100, ActorRole.PLATFORM_ADMIN)
        self.guest = Actor(self.fix["guest_id"], ActorRole.CUSTOMER)

    def tearDown(self) -> None:
        self._stack.close()

    def available(self, day: str) -> int:
        """读某日可售量。"""
        row = self.conn.execute(
            "SELECT available_rooms FROM room_inventory WHERE room_type_id = ? AND stay_date = ?",
            (self.fix["room_type_id"], day),
        ).fetchone()
        return int(row["available_rooms"])

    def status_of(self, day: str) -> str:
        """读某日销售状态。"""
        row = self.conn.execute(
            "SELECT sale_status FROM room_inventory WHERE room_type_id = ? AND stay_date = ?",
            (self.fix["room_type_id"], day),
        ).fetchone()
        return str(row["sale_status"])

    def test_调整可售房量并写审计(self) -> None:
        self.service.adjust_available(
            self.fix["room_type_id"], datetime(2027, 3, 2).date(), 3, self.staff
        )
        self.assertEqual(self.available("2027-03-02"), 3)

        audit = self.conn.execute(
            "SELECT action, before_state, after_state, operator_role FROM audit_log"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(audit["action"], "ADJUST_AVAILABLE")
        self.assertEqual(audit["before_state"], "5")
        self.assertEqual(audit["after_state"], "3")
        self.assertEqual(audit["operator_role"], "HOTEL")

    def test_可售不能小于已占用(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self.service.adjust_available(
                self.fix["room_type_id"], datetime(2027, 3, 1).date(), 1, self.staff
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")
        self.assertEqual(self.available("2027-03-01"), 5)

    def test_可售不能超过总房量(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.adjust_available(
                self.fix["room_type_id"], datetime(2027, 3, 2).date(), 6, self.staff
            )
        self.assertEqual(self.available("2027-03-02"), 5)

    def test_顾客不能改库存(self) -> None:
        with self.assertRaises(PermissionDeniedError):
            self.service.adjust_available(
                self.fix["room_type_id"], datetime(2027, 3, 2).date(), 4, self.guest
            )

    def test_停售与复售(self) -> None:
        self.service.suspend_day(
            self.fix["room_type_id"], datetime(2027, 3, 2).date(), self.staff, "装修"
        )
        self.assertEqual(self.status_of("2027-03-02"), "SUSPENDED")

        self.service.resume_day(self.fix["room_type_id"], datetime(2027, 3, 2).date(), self.staff)
        self.assertEqual(self.status_of("2027-03-02"), "ON_SALE")

    def test_管理员可以改任意酒店库存(self) -> None:
        self.service.adjust_available(
            self.fix["room_type_id"], datetime(2027, 3, 2).date(), 4, self.admin
        )
        self.assertEqual(self.available("2027-03-02"), 4)


if __name__ == "__main__":
    unittest.main()
