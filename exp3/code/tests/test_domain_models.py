"""实体用例：构造校验、派生量口径、状态写入口的唯一性。"""

from __future__ import annotations

import unittest
from datetime import date

from app.domain.enums import BookingStatus
from app.domain.errors import InvalidStateError, ValidationError
from app.domain.models import (
    AuditLog,
    Booking,
    BookingNight,
    HolidayCalendar,
    Hotel,
    RoomInventory,
    RoomType,
    UserAccount,
)


def make_booking(**overrides) -> Booking:
    """构造一张合法订单，按需覆盖字段。"""
    params = {
        "booking_no": "B-M-0001",
        "guest_id": 1,
        "hotel_id": 1,
        "room_type_id": 1,
        "check_in_date": date(2027, 3, 1),
        "check_out_date": date(2027, 3, 4),
        "room_count": 2,
        "total_price_cents": 186000,
        "status": BookingStatus.PENDING,
    }
    params.update(overrides)
    return Booking(**params)


class BookingValidationTest(unittest.TestCase):
    """构造即校验：脏数据不允许进入领域对象。"""

    def test_间数为零或负数被拒(self) -> None:
        """0 间与 −1 间都是 422。"""
        for room_count in (0, -1):
            with self.subTest(room_count=room_count):
                with self.assertRaises(ValidationError):
                    make_booking(room_count=room_count)

    def test_退房日不晚于入住日被拒(self) -> None:
        """同日退房与倒序日期都在构造阶段被拒。"""
        with self.assertRaises(ValidationError):
            make_booking(check_out_date=date(2027, 3, 1))
        with self.assertRaises(ValidationError):
            make_booking(check_out_date=date(2027, 2, 27))

    def test_负总价被拒(self) -> None:
        """金额不允许为负（0 元单允许存在，用于兑换/赠送场景）。"""
        with self.assertRaises(ValidationError):
            make_booking(total_price_cents=-1)
        self.assertEqual(make_booking(total_price_cents=0).total_price_cents, 0)


class BookingDerivedTest(unittest.TestCase):
    """派生量：天数、逐晚日期、有效性、终态，全部是方法/属性，不落库。"""

    def test_天数与逐晚日期(self) -> None:
        """3/1 入住、3/4 退房 → 3 晚、日期到 3/3 为止。"""
        booking = make_booking()
        self.assertEqual(booking.nights_count, 3)
        self.assertEqual(
            booking.stay_dates,
            [date(2027, 3, 1), date(2027, 3, 2), date(2027, 3, 3)],
        )

    def test_有效与终态口径(self) -> None:
        """待确认/已确认/已入住算有效；已退房/已取消/未入住算终态。"""
        for status in (
            BookingStatus.PENDING,
            BookingStatus.CONFIRMED,
            BookingStatus.CHECKED_IN,
        ):
            with self.subTest(status=status.value):
                booking = make_booking(status=status)
                self.assertTrue(booking.is_active)
                self.assertFalse(booking.is_terminal)
        for status in (
            BookingStatus.CHECKED_OUT,
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
        ):
            with self.subTest(status=status.value):
                booking = make_booking(status=status)
                self.assertFalse(booking.is_active)
                self.assertTrue(booking.is_terminal)

    def test_按逐晚快照重算总价(self) -> None:
        """快照之和与订单总价一致时，对账才算通过。"""
        booking = make_booking(
            nights=[
                BookingNight(1, date(2027, 3, 1), 30000, 2),
                BookingNight(1, date(2027, 3, 2), 33000, 2),
                BookingNight(1, date(2027, 3, 3), 30000, 2),
            ]
        )
        self.assertEqual(booking.recompute_total_price(), 186000)


class BookingStatusWriteTest(unittest.TestCase):
    """``apply_status`` 是唯一写入口，只接受枚举成员。"""

    def test_写入枚举成员成功(self) -> None:
        """状态机给出目标状态后由实体落值。"""
        booking = make_booking()
        booking.apply_status(BookingStatus.CONFIRMED)
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)

    def test_写入裸字符串被拒(self) -> None:
        """绕过枚举直接写 ``"CONFIRMED"`` 必须报 500，防止状态来源不可控。"""
        booking = make_booking()
        with self.assertRaises(InvalidStateError) as raised:
            booking.apply_status("CONFIRMED")  # type: ignore[arg-type]
        self.assertEqual(raised.exception.http_status, 500)
        self.assertEqual(booking.status, BookingStatus.PENDING)


class RoomInventoryTest(unittest.TestCase):
    """库存行：余量派生、在售判定、占用与调整的边界。"""

    def test_余量与在售(self) -> None:
        """余量 = 可售 − 占用；停售行的余量照算但不可占用。"""
        row = RoomInventory(1, date(2027, 3, 1), 5, 2)
        self.assertEqual(row.remaining, 3)
        self.assertTrue(row.is_on_sale)
        self.assertTrue(row.can_occupy(3))
        self.assertFalse(row.can_occupy(4))
        self.assertFalse(row.can_occupy(0))

    def test_停售行不可占用(self) -> None:
        """停售日即使余量充足也拒绝占用。"""
        row = RoomInventory(1, date(2027, 3, 1), 5, 0, sale_status="SUSPENDED")
        self.assertFalse(row.is_on_sale)
        self.assertFalse(row.can_occupy(1))

    def test_可售量不得降到已占用以下(self) -> None:
        """调整挂牌量时，新可售低于已占用会让余量为负，必须挡住。"""
        row = RoomInventory(1, date(2027, 3, 1), 5, 3)
        self.assertTrue(row.can_adjust_available(3))
        self.assertFalse(row.can_adjust_available(2))


class RoomTypeTest(unittest.TestCase):
    """跨表规则：占用不得超过总房量（行内 CHECK 表达不了，靠这里把关）。"""

    def test_占用超过总房量抛错(self) -> None:
        """总房量 6、占用 7 → 500 级数据不自洽。"""
        room_type = RoomType(1, 1, "标准双床", "双床", 28, 2, 6)
        self.assertFalse(room_type.occupied_exceeds_total(6))
        self.assertTrue(room_type.occupied_exceeds_total(7))
        room_type.assert_occupied_within_total(6)
        with self.assertRaises(InvalidStateError):
            room_type.assert_occupied_within_total(7)


class SmallEntitiesTest(unittest.TestCase):
    """其余小实体的判定与摘要方法。"""

    def test_账号口令校验走注入的校验函数(self) -> None:
        """领域层不依赖加密实现：只调用 ``verifier``，便于用假实现单测。"""
        account = UserAccount(1, "13800000001", "hash", "CUSTOMER")
        self.assertTrue(account.is_enabled)
        self.assertTrue(account.verify_password("Passw0rd!", lambda raw, hashed: hashed == "hash"))
        self.assertFalse(account.verify_password("wrong", lambda raw, hashed: False))

    def test_酒店审核状态(self) -> None:
        """只有 ``APPROVED`` 才算通过审核。"""
        self.assertFalse(Hotel(1, "云栖酒店", "杭州", "021").is_approved)
        self.assertTrue(Hotel(1, "云栖酒店", "杭州", "021", audit_status="APPROVED").is_approved)

    def test_审计摘要与节假日开关(self) -> None:
        """审计摘要形如 ``CANCEL: CONFIRMED → CANCELLED``。"""
        log = AuditLog(
            operator_id=1,
            operator_role="CUSTOMER",
            target_type="BOOKING",
            target_id="B-M-0001",
            action="CANCEL",
            before_state="CONFIRMED",
            after_state="CANCELLED",
        )
        self.assertEqual(log.describe(), "CANCEL: CONFIRMED → CANCELLED")
        self.assertEqual(
            AuditLog(1, "SYSTEM", "BOOKING", "B-M-0001", "TIMEOUT").describe(),
            "TIMEOUT: - → -",
        )
        self.assertTrue(HolidayCalendar(date(2027, 1, 1), "元旦").is_enabled)
        self.assertFalse(
            HolidayCalendar(date(2027, 1, 1), "元旦", status="DISABLED").is_enabled
        )


if __name__ == "__main__":
    unittest.main()
