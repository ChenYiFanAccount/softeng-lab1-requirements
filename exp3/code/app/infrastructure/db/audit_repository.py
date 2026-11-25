"""``idempotency_key`` 与 ``audit_log`` 的 SQLite 实现。

幂等键的语义（S3-3）：同一键重复提交两次，只产生 1 张订单，且**返回同一订单号**。
实现上把"查键 → 建单 → 写键"放进同一个 ``BEGIN IMMEDIATE`` 事务：并发同键的
第二个线程会阻塞到第一个提交，再看键就已存在，直接返回原订单号。

审计只追加：本类只提供 ``append`` 与 ``query``，**没有** update/delete 方法，
S4-4 会用 ``grep 'delete from audit_log'`` 反向确认代码里也没有。
"""

from __future__ import annotations

import sqlite3

from app.domain.models import AuditLog
from app.domain.repositories import AuditLogRepository
from app.infrastructure.db.mapping import parse_time, time_text


class SqliteIdempotencyRepository:
    """幂等键表：键 → 订单号（弱引用，避免与 ``booking`` 成环）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key_value: str) -> str | None:
        """取键对应的订单号；键不存在返回 None。"""
        row = self._conn.execute(
            "SELECT booking_no FROM idempotency_key WHERE key_value = ?",
            (key_value,),
        ).fetchone()
        if row is None or row["booking_no"] is None:
            return None
        return str(row["booking_no"])

    def put(self, key_value: str, booking_no: str) -> None:
        """登记键与订单号的对应关系。"""
        self._conn.execute(
            "INSERT INTO idempotency_key (key_value, booking_no, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT (key_value) DO UPDATE SET booking_no = excluded.booking_no",
            (key_value, booking_no, time_text(None)),
        )


class SqliteAuditLogRepository(AuditLogRepository):
    """审计仓储：只追加、可按键查；不提供修改与删除。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, log: AuditLog) -> AuditLog:
        """追加一条审计；返回带主键的对象。"""
        cursor = self._conn.execute(
            "INSERT INTO audit_log (operator_id, operator_role, target_type, target_id, action, "
            "before_state, after_state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                log.operator_id,
                log.operator_role,
                log.target_type,
                log.target_id,
                log.action,
                log.before_state,
                log.after_state,
                time_text(log.created_at),
            ),
        )
        log.log_id = int(cursor.lastrowid)
        return log

    def query(self, target_type: str, target_id: str, limit: int = 50) -> list[AuditLog]:
        """按对象取审计（新记录在前）。"""
        rows = self._conn.execute(
            "SELECT id, operator_id, operator_role, target_type, target_id, action, "
            "before_state, after_state, created_at FROM audit_log "
            "WHERE target_type = ? AND target_id = ? ORDER BY id DESC LIMIT ?",
            (target_type, str(target_id), limit),
        ).fetchall()
        return [
            AuditLog(
                operator_id=int(row["operator_id"]),
                operator_role=str(row["operator_role"]),
                target_type=str(row["target_type"]),
                target_id=str(row["target_id"]),
                action=str(row["action"]),
                before_state=row["before_state"],
                after_state=row["after_state"],
                created_at=parse_time(row["created_at"]),
                log_id=int(row["id"]),
            )
            for row in rows
        ]

    def count(self) -> int:
        """审计总条数（用例断言"失败也留痕"时用）。"""
        return int(self._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])
