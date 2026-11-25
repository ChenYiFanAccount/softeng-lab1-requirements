"""酒店审核状态的写入仓储（M9 平台管理用）。

只做一件事：改 ``hotel.audit_status`` 与 ``reject_reason``。审核的业务规则
（谁能审、理由必填、审计留痕）在应用层 ``AdminService`` 里，仓储不管权限。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from app.infrastructure.db.mapping import time_text


class SqliteHotelAdminRepository:
    """酒店审核状态的读写。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def audit_status(self, hotel_id: int) -> str | None:
        """当前审核状态；酒店不存在时返回 None。"""
        row = self._conn.execute(
            "SELECT audit_status FROM hotel WHERE id = ?", (hotel_id,)
        ).fetchone()
        return None if row is None else str(row["audit_status"])

    def set_audit_status(
        self,
        hotel_id: int,
        audit_status: str,
        reject_reason: str | None,
        audited_at: datetime | None = None,
    ) -> None:
        """写入审核结果；表上有 CHECK，``REJECTED`` 必须同时给理由。"""
        self._conn.execute(
            "UPDATE hotel SET audit_status = ?, reject_reason = ?, audited_at = ? WHERE id = ?",
            (audit_status, reject_reason, time_text(audited_at), hotel_id),
        )
