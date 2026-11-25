"""平台管理（M9）：酒店审核与账号查看。

规矩只有三条，都写在这里而不是界面里：
1. 只有平台管理员能动审核状态；
2. 驳回必须给理由（表上有 CHECK，但错误要变成 422 而不是 SQL 异常）；
3. 每次审核写一条审计，action 用 ``HOTEL_APPROVE`` / ``HOTEL_REJECT``。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from app.application.actor import Actor
from app.application.clock import Clock, SystemClock
from app.domain.enums import HotelAuditStatus
from app.domain.errors import PermissionDeniedError, ValidationError
from app.domain.models import AuditLog
from app.infrastructure.db.audit_repository import SqliteAuditLogRepository
from app.infrastructure.db.catalog_query_repository import (
    AccountRow,
    HotelRow,
    SqliteCatalogQueryRepository,
)
from app.infrastructure.db.hotel_repository import SqliteHotelAdminRepository


@dataclass(frozen=True, slots=True)
class AuditOutcome:
    """一次审核的结果（界面用来刷新列表并提示）。"""

    hotel_id: int
    audit_status: str
    reject_reason: str | None


class AdminService:
    """酒店审核 + 账号查看；写操作均带权限校验与审计。"""

    def __init__(self, conn: sqlite3.Connection, clock: Clock | None = None) -> None:
        self._catalog = SqliteCatalogQueryRepository(conn)
        self._hotels = SqliteHotelAdminRepository(conn)
        self._audits = SqliteAuditLogRepository(conn)
        self._clock: Clock = clock or SystemClock()

    def list_hotels(self, audit_status: str | None = None) -> list[HotelRow]:
        """全部酒店（可按审核状态过滤），待审在前。"""
        rows = self._catalog.all_hotels(audit_status)
        return sorted(rows, key=lambda row: (row.audit_status != "PENDING", row.hotel_id))

    def list_accounts(self, role: str | None = None) -> list[AccountRow]:
        """账号列表；不含密码散列。"""
        return self._catalog.accounts(role)

    def approve(self, hotel_id: int, actor: Actor) -> AuditOutcome:
        """审核通过。"""
        return self._decide(hotel_id, actor, HotelAuditStatus.APPROVED, None)

    def reject(self, hotel_id: int, actor: Actor, reason: str) -> AuditOutcome:
        """审核驳回；理由不能为空。"""
        text = (reason or "").strip()
        if not text:
            raise ValidationError("驳回必须填写理由", hotel_id=hotel_id)
        return self._decide(hotel_id, actor, HotelAuditStatus.REJECTED, text)

    def _decide(
        self,
        hotel_id: int,
        actor: Actor,
        target: HotelAuditStatus,
        reason: str | None,
    ) -> AuditOutcome:
        if not actor.is_admin:
            raise PermissionDeniedError("只有平台管理员可以审核酒店", hotel_id=hotel_id)
        before = self._hotels.audit_status(hotel_id)
        if before is None:
            raise ValidationError("酒店不存在", hotel_id=hotel_id)
        stamp: datetime = self._clock.now()
        self._hotels.set_audit_status(hotel_id, target.value, reason, stamp)
        self._audits.append(
            AuditLog(
                operator_id=actor.account_id,
                operator_role="ADMIN",
                target_type="HOTEL",
                target_id=str(hotel_id),
                action=f"HOTEL_{target.value}",
                created_at=stamp,
                before_state=before,
                after_state=target.value,
                reason=reason,
            )
        )
        return AuditOutcome(hotel_id=hotel_id, audit_status=target.value, reject_reason=reason)
