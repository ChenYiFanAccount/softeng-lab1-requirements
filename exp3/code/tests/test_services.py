"""领域服务用例：用内存假仓储跑通"校验 → 建单 → 流转 → 审计"，不连数据库。

这组用例同时是 S3 的预演：应用层只需把假仓储换成 SQLite 实现，再包一层事务。
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
from app.domain.errors import (
    IllegalTransitionError,
    NoAvailabilityError,
    PermissionDeniedError,
    ValidationError,
)
from app.domain.models import AuditLog, Booking, RoomInventory, RoomType
from app.domain.repositories import (
    AuditLogRepository,
    BookingRepository,
    InventoryRepository,
)
from app.domain.services import BookingService, InventoryService


class FakeInventoryRepository(InventoryRepository):
    """内存库存：``{(room_type_id, stay_date): RoomInventory}``。"""

    def __init__(self) -> None:
        self.rows: dict[tuple[int, date], RoomInventory] = {}

    def put(self, room_type_id: int, stay_date: str, available: int, occupied: int = 0,
            status: str = "ON_SALE") -> None:
        """塞一行库存（日期用 ISO 字符串写）。"""
        parsed = date.fromisoformat(stay_date)
        self.rows[(room_type_id, parsed)] = RoomInventory(
            room_type_id=room_type_id,
            stay_date=parsed,
            available_rooms=available,
            occupied_rooms=occupied,
            sale_status=status,
        )

    def lock_rows(self, room_type_id: int, dates: list[date]) -> list[RoomInventory]:
        """按日期顺序返回已存在的行（缺行不补）。"""
        return [self.rows[key] for key in ((room_type_id, item) for item in dates)
                if key in self.rows]

    def add_occupied(self, room_type_id: int, stay_date: date, delta: int) -> None:
        """增量改占用。"""
        row = self.rows[(room_type_id, stay_date)]
        row.occupied_rooms += delta

    def range_remaining(self, room_type_id: int, dates: list[date]) -> list[int]:
        """逐日余量；缺行按 0。"""
        return [self.rows[(room_type_id, item)].remaining if (room_type_id, item) in self.rows
                else 0 for item in dates]


class FakeBookingRepository(BookingRepository):
    """内存订单仓：按订单号存。"""

    def __init__(self) -> None:
        self.saved: list[Booking] = []

    def get_by_no(self, booking_no: str) -> Booking | None:
        """按订单号取。"""
        return next((item for item in self.saved if item.booking_no == booking_no), None)

    def save(self, booking: Booking) -> None:
        """记录一次保存。"""
        self.saved.append(booking)

    def find_active_overlap(self, guest_id: int, hotel_id: int, room_type_id: int,
                            check_in_date: date, check_out_date: date) -> list[Booking]:
        """类图要求的重叠查询；本组用例不涉及，返回空列表。"""
        return []


class FakeAuditRepository(AuditLogRepository):
    """内存审计：只追加。"""

    def __init__(self) -> None:
        self.logs: list[AuditLog] = []

    def append(self, log: AuditLog) -> None:
        """追加一条。"""
        self.logs.append(log)

    def query(self, target_type: str, target_id: str, limit: int = 50) -> list[AuditLog]:
        """按对象过滤。"""
        hits = [log for log in self.logs if log.target_id == target_id]
        return hits[-limit:]


class InventoryServiceTest(unittest.TestCase):
    """库存服务的余量口径与挂牌量校验。"""

    def setUp(self) -> None:
        self.repo = FakeInventoryRepository()
        self.repo.put(1, "2027-03-01", 5, 2)
        self.repo.put(1, "2027-03-02", 3, 3)
        self.room_type = RoomType(1, 1, "标准双床", "双床", 28, 2, 6)
        self.service = InventoryService(self.repo, lambda room_type_id: self.room_type)

    def test_区间余量取各日最小值(self) -> None:
        """3/1 余 3、3/2 余 0 → 区间上限 0；空区间 0。"""
        dates = [date(2027, 3, 1), date(2027, 3, 2)]
        self.assertEqual(self.service.remaining(1, dates), 0)
        self.assertEqual(self.service.remaining(1, []), 0)

    def test_可订校验失败时抛出日期细节(self) -> None:
        """第二晚已满，请求 1 间 → 409 且 details 指向 3/2。"""
        with self.assertRaises(NoAvailabilityError) as raised:
            self.service.ensure_available(1, 1, [date(2027, 3, 1), date(2027, 3, 2)])
        self.assertEqual(raised.exception.details["stay_date"], "2027-03-02")

    def test_调整挂牌量的三条边界(self) -> None:
        """负数 422、超过总房量 422、合法值放行。"""
        with self.assertRaises(ValidationError):
            self.service.ensure_can_adjust(1, -1)
        with self.assertRaises(ValidationError) as raised:
            self.service.ensure_can_adjust(1, 7)
        self.assertEqual(raised.exception.details["total_rooms"], 6)
        self.service.ensure_can_adjust(1, 6)


class BookingServiceTest(unittest.TestCase):
    """预订服务：建单、状态流转、审计落账。"""

    def setUp(self) -> None:
        self.inventories = FakeInventoryRepository()
        self.inventories.put(1, "2027-03-01", 5, 0)
        self.inventories.put(1, "2027-03-02", 5, 0)
        self.bookings = FakeBookingRepository()
        self.audits = FakeAuditRepository()
        self.service = BookingService(
            self.bookings,
            InventoryService(self.inventories),
            self.audits,
        )
        self.prices = {date(2027, 3, 1): 30000, date(2027, 3, 2): 32000}

    def _draft(self, room_count: int = 2) -> Booking:
        return self.service.draft(
            booking_no="B-SVC-0001",
            guest_id=1,
            hotel_id=1,
            room_type_id=1,
            check_in_date=date(2027, 3, 1),
            check_out_date=date(2027, 3, 3),
            room_count=room_count,
            nightly_prices=self.prices,
        )

    def test_建单得到待确认订单与逐晚快照(self) -> None:
        """总价 (300+320)×2=124000 分，状态 PENDING，两晚快照。"""
        booking = self._draft()
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertEqual(booking.total_price_cents, 124000)
        self.assertEqual(booking.recompute_total_price(), 124000)
        self.assertEqual(len(booking.nights), 2)

    def test_余量不足时建单被拒(self) -> None:
        """请求 6 间但只有 5 间 → 409，且不产生订单对象。"""
        with self.assertRaises(NoAvailabilityError):
            self._draft(room_count=6)

    def test_确认流转并写审计(self) -> None:
        """酒店确认：状态变已确认、订单被保存、审计记录 T1。"""
        booking = self._draft()
        edge = self.service.apply_event(
            booking,
            BookingEvent.CONFIRM,
            role=ActorRole.HOTEL_STAFF,
            operator_id=3,
        )
        self.assertEqual(edge.code, "T1")
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)
        self.assertEqual(len(self.bookings.saved), 1)
        log = self.audits.logs[-1]
        self.assertEqual(log.action, "T1")
        self.assertEqual(log.before_state, "PENDING")
        self.assertEqual(log.after_state, "CONFIRMED")
        self.assertEqual(log.target_id, "B-SVC-0001")

    def test_无权操作时不保存也不写审计(self) -> None:
        """顾客替酒店确认 → 403，订单与审计都不动。"""
        booking = self._draft()
        with self.assertRaises(PermissionDeniedError):
            self.service.apply_event(
                booking,
                BookingEvent.CONFIRM,
                role=ActorRole.CUSTOMER,
                operator_id=1,
            )
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertEqual(self.bookings.saved, [])
        self.assertEqual(self.audits.logs, [])

    def test_取消时记录原因与发起人(self) -> None:
        """T6 取消写 cancel_reason / cancel_initiator。

        注意边界：顾客只能取消**已确认**的订单；待确认单要等酒店拒单（T2）或超时（T3），
        所以这里先让酒店确认，再由顾客取消。
        """
        booking = self._draft()
        self.service.apply_event(
            booking,
            BookingEvent.CONFIRM,
            role=ActorRole.HOTEL_STAFF,
            operator_id=3,
        )
        self.service.apply_event(
            booking,
            BookingEvent.CANCEL,
            role=ActorRole.CUSTOMER,
            operator_id=1,
            reason="行程变更",
        )
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual(booking.cancel_reason, "行程变更")
        self.assertEqual(booking.cancel_initiator, ActorRole.CUSTOMER.value)

    def test_待确认订单不能被顾客取消(self) -> None:
        """待确认 + CANCEL 没有对应边 → 409，提示走拒单或超时。"""
        booking = self._draft()
        with self.assertRaises(IllegalTransitionError):
            self.service.apply_event(
                booking,
                BookingEvent.CANCEL,
                role=ActorRole.CUSTOMER,
                operator_id=1,
            )
        self.assertEqual(booking.status, BookingStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
