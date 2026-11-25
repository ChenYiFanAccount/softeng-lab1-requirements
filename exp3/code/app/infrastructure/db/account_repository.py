"""账号写入仓储（注册用）：只做 INSERT 与状态更新。

密码散列由应用层算好再传进来——仓储不该知道 PBKDF2 的迭代次数，
否则"改成本参数"要同时改两层。
"""

from __future__ import annotations

import sqlite3

from app.infrastructure.db.mapping import time_text


class SqliteAccountWriter:
    """账号的新增与状态变更。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def exists(self, login_name: str) -> bool:
        """手机号是否已注册。"""
        row = self._conn.execute(
            "SELECT 1 FROM user_account WHERE login_name = ?", (login_name,)
        ).fetchone()
        return row is not None

    def create(
        self,
        login_name: str,
        password_hash: str,
        role: str = "CUSTOMER",
        hotel_id: int | None = None,
    ) -> int:
        """插入账号并返回主键；唯一约束由数据库兜底。"""
        cursor = self._conn.execute(
            "INSERT INTO user_account "
            "(login_name, password_hash, role, hotel_id, status, created_at) "
            "VALUES (?, ?, ?, ?, 'ACTIVE', ?)",
            (
                login_name,
                password_hash,
                role,
                hotel_id,
                time_text(None),
            ),  # noqa: E501
        )
        return int(cursor.lastrowid)

    def set_status(self, login_name: str, status: str) -> None:
        """启用 / 停用账号。"""
        self._conn.execute(
            "UPDATE user_account SET status = ? WHERE login_name = ?", (status, login_name)
        )
