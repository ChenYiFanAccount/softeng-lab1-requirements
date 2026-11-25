"""仓储接口：领域层**定义**、数据访问层**实现**（依赖倒置的唯一一处反向箭头）。

为什么接口放领域层：应用服务要能在不连数据库的情况下被单测（用内存实现替换），
而 SQLite 只是"一种实现"。因此 ``app/domain`` 只认这三个抽象类，
``app/infrastructure/repositories`` 才 import ``sqlite3``。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.domain.models import AuditLog, Booking, RoomInventory


class BookingRepository(ABC):
    """订单仓储（对应类图 ``BookingRepository``）。"""

    @abstractmethod
    def get_by_no(self, booking_no: str) -> Booking | None:
        """按订单号查订单；不存在返回 ``None``。"""

    @abstractmethod
    def save(self, booking: Booking) -> None:
        """新增或更新订单（含逐晚快照）。实现方必须在事务内调用。"""

    @abstractmethod
    def find_active_overlap(
        self,
        guest_id: int,
        hotel_id: int,
        room_type_id: int,
        check_in_date: date,
        check_out_date: date,
    ) -> list[Booking]:
        """查同顾客+同酒店+同房型在**日期重叠**的有效订单（区间判定在实现里做）。

        注意：``ux_booking_active_period`` 只拦起止日完全相同的重复，重叠区间
        必须靠这个方法在事务内复核（S1 交付说明 D2）。
        """


class InventoryRepository(ABC):
    """库存仓储（对应类图 ``InventoryRepository``）。"""

    @abstractmethod
    def lock_rows(self, room_type_id: int, dates: list[date]) -> list[RoomInventory]:
        """在写事务内读取并锁定「房型 × 日期」的库存行。

        返回顺序与 ``dates`` 一致；缺行必须显式表现为空列表而不是"默认无限"。
        """

    @abstractmethod
    def add_occupied(self, room_type_id: int, stay_date: date, delta: int) -> None:
        """对某日已占用做增量更新（``delta`` 可正可负：下单 +n、取消 −n）。"""

    @abstractmethod
    def range_remaining(self, room_type_id: int, dates: list[date]) -> list[int]:
        """按日期返回余量列表，供界面显示与压测断言。"""


class AuditLogRepository(ABC):
    """审计日志仓储（对应类图 ``AuditLogRepository``，只追加）。"""

    @abstractmethod
    def append(self, log: AuditLog) -> None:
        """追加一条审计记录（不更新、不删除）。"""

    @abstractmethod
    def query(self, target_type: str, target_id: str, limit: int = 50) -> list[AuditLog]:
        """按对象查审计轨迹，按时间倒序返回至多 ``limit`` 条。"""
