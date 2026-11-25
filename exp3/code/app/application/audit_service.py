"""审计查询（M10 的只读一侧）：只提供查询，没有任何修改或删除方法。"""

from __future__ import annotations

import sqlite3

from app.domain.models import AuditLog
from app.infrastructure.db.audit_repository import SqliteAuditLogRepository

DEFAULT_LIMIT = 200


class AuditService:
    """审计日志只读查询；按对象类型与对象 ID 过滤。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._audits = SqliteAuditLogRepository(conn)

    def query(
        self,
        target_type: str,
        target_id: str = "",
        limit: int = DEFAULT_LIMIT,
    ) -> list[AuditLog]:
        """取最近若干条；``target_id`` 为空表示该类型全部对象。"""
        if not (target_id or "").strip():
            return self._audits.list_recent(target_type, limit=limit)
        return self._audits.query(target_type, target_id, limit=limit)

    def count(self) -> int:
        """审计总条数（首页概览用）。"""
        return self._audits.count()
