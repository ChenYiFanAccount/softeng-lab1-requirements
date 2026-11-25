"""库存应用服务：酒店员工调整可售房量与停售/复售（M2 纵切）。

领域层的 ``RoomInventory`` 只知道"可售 ≥ 占用"这一条；"可售 ≤ 总房量"要靠
``RoomType.total_rooms`` 才能判，所以这条校验放在应用服务里做——
这是 S1 交付说明 D3 登记的既有偏差，不是这里新引入的。
"""

from __future__ import annotations

import sqlite3
from datetime import date

from app.application.actor import Actor
from app.application.clock import Clock, SystemClock
from app.application.errors import bad_request
from app.domain.enums import ActorRole
from app.domain.errors import PermissionDeniedError, ValidationError
from app.domain.models import AuditLog
from app.infrastructure.db.audit_repository import SqliteAuditLogRepository
from app.infrastructure.db.connection import immediate_transaction
from app.infrastructure.db.inventory_repository import SqliteInventoryRepository
from app.infrastructure.db.mapping import date_text

#: 审计里 ``operator_role`` 的短码（与订单审计保持同一词表）
ROLE_CODE = {
    ActorRole.CUSTOMER: "CUSTOMER",
    ActorRole.HOTEL_STAFF: "HOTEL",
    ActorRole.PLATFORM_ADMIN: "ADMIN",
    ActorRole.SYSTEM: "SYSTEM",
}


class InventoryAppService:
    """酒店侧库存维护：调可售、停售、复售，全部写审计。"""

    def __init__(self, conn: sqlite3.Connection, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock or SystemClock()
        self._inventories = SqliteInventoryRepository(conn)
        self._audits = SqliteAuditLogRepository(conn)

    def adjust_available(
        self,
        room_type_id: int,
        stay_date: date,
        new_available: int,
        actor: Actor,
    ) -> None:
        """把某日可售房量改成 ``new_available``。

        校验顺序：①操作者必须是该房型所属酒店的员工或平台管理员；
        ②``new_available`` 不得小于当日已占用（否则等于把已卖出的房抹掉）；
        ③``new_available`` 不得超过房型总房量。

        Args:
            room_type_id: 房型。
            stay_date: 具体某一天。
            new_available: 目标可售房量。
            actor: 操作者。

        Raises:
            PermissionDeniedError: 非本酒店员工。
            ValidationError: 越界或该日无库存行。
        """
        hotel_id, total_rooms = self._room_type_scope(room_type_id)
        self._assert_staff(actor, hotel_id)
        with immediate_transaction(self._conn):
            inventory = self._lock_one(room_type_id, stay_date)
            if new_available < inventory.occupied_rooms:
                raise ValidationError(
                    "可售房量不能小于当日已占用",
                    room_type_id=room_type_id,
                    stay_date=date_text(stay_date),
                    occupied=inventory.occupied_rooms,
                    requested=new_available,
                )
            if new_available > total_rooms:
                raise ValidationError(
                    "可售房量不能超过房型总房量",
                    room_type_id=room_type_id,
                    stay_date=date_text(stay_date),
                    total_rooms=total_rooms,
                    requested=new_available,
                )
            self._inventories.set_available(room_type_id, stay_date, new_available)
            self._audit(
                room_type_id,
                stay_date,
                "ADJUST_AVAILABLE",
                str(inventory.available_rooms),
                str(new_available),
                actor,
            )

    def suspend_day(
        self,
        room_type_id: int,
        stay_date: date,
        actor: Actor,
        reason: str = "",
    ) -> None:
        """停售某日（已卖出的房不受影响，新单会被拒）。"""
        self._switch_sale_status(room_type_id, stay_date, actor, "SUSPENDED", reason)

    def resume_day(
        self,
        room_type_id: int,
        stay_date: date,
        actor: Actor,
        reason: str = "",
    ) -> None:
        """恢复某日销售。"""
        self._switch_sale_status(room_type_id, stay_date, actor, "ON_SALE", reason)

    def _switch_sale_status(
        self,
        room_type_id: int,
        stay_date: date,
        actor: Actor,
        target: str,
        reason: str,
    ) -> None:
        hotel_id, _ = self._room_type_scope(room_type_id)
        self._assert_staff(actor, hotel_id)
        with immediate_transaction(self._conn):
            inventory = self._lock_one(room_type_id, stay_date)
            if inventory.sale_status == target:
                return
            self._inventories.set_sale_status(room_type_id, stay_date, target)
            self._audit(
                room_type_id,
                stay_date,
                f"SALE_STATUS_{target}",
                inventory.sale_status,
                target,
                actor,
                reason,
            )

    def _lock_one(self, room_type_id: int, stay_date: date):
        """取一行库存；不存在直接 422（说明日历没铺到这一天）。"""
        rows = self._inventories.lock_rows(room_type_id, [stay_date])
        if not rows:
            raise bad_request(
                "该日期没有库存记录",
                room_type_id=room_type_id,
                stay_date=date_text(stay_date),
            )
        return rows[0]

    def _room_type_scope(self, room_type_id: int) -> tuple[int, int]:
        """取房型所属酒店与总房量。"""
        row = self._conn.execute(
            "SELECT hotel_id, total_rooms FROM room_type WHERE id = ?",
            (room_type_id,),
        ).fetchone()
        if row is None:
            raise bad_request("房型不存在", room_type_id=room_type_id)
        return int(row["hotel_id"]), int(row["total_rooms"])

    @staticmethod
    def _assert_staff(actor: Actor, hotel_id: int) -> None:
        """只有本酒店员工或平台管理员能改库存。"""
        if actor.is_admin:
            return
        if not actor.works_at(hotel_id):
            raise PermissionDeniedError(
                "只能维护本酒店的库存",
                hotel_id=hotel_id,
                actor_id=actor.account_id,
            )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def _audit(
        self,
        room_type_id: int,
        stay_date: date,
        action: str,
        before: str,
        after: str,
        actor: Actor,
        reason: str = "",
    ) -> None:
        """写一条库存审计（``audit_log`` 没有 reason 列，reason 只进订单表）。"""
        self._audits.append(
            AuditLog(
                operator_id=actor.account_id,
                operator_role=ROLE_CODE[actor.role],
                target_type="ROOM_INVENTORY",
                target_id=f"{room_type_id}:{date_text(stay_date)}",
                action=action,
                before_state=before,
                after_state=after,
                created_at=self._clock.now(),
                reason=reason or None,
            )
        )
