"""自助注册（M9 的顾客侧入口）：游客注册成为顾客账号。

规则：
- 手机号必须 11 位数字（与种子账号同一口径，登录名即手机号）；
- 密码至少 8 位，至少含字母与数字各一（课程演示账号 ``Passw0rd!`` 满足）；
- 注册出来的角色只能是 ``CUSTOMER``——员工账号由平台管理员建，不给自助开通。
"""

from __future__ import annotations

import re
import sqlite3

from app.application.actor import Actor
from app.domain.enums import ActorRole
from app.domain.errors import ValidationError
from app.infrastructure.db.account_repository import SqliteAccountWriter
from app.infrastructure.security import hash_password, new_salt

PHONE_PATTERN = re.compile(r"^\d{11}$")
MIN_PASSWORD = 8


class AccountService:  # pylint: disable=too-few-public-methods
    """注册与改密之外的最小账号能力。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._accounts = SqliteAccountWriter(conn)

    def register(self, login_name: str, password: str, confirm: str | None = None) -> Actor:
        """注册顾客账号并返回可直接登录的操作者。"""
        phone = (login_name or "").strip()
        if not PHONE_PATTERN.match(phone):
            raise ValidationError("手机号必须是 11 位数字")
        if confirm is not None and confirm != password:
            raise ValidationError("两次输入的密码不一致")
        _check_password(password)
        if self._accounts.exists(phone):
            raise ValidationError("该手机号已注册，请直接登录")
        salt = new_salt()
        account_id = self._accounts.create(phone, hash_password(password, salt))
        return Actor(account_id=account_id, role=ActorRole.CUSTOMER, login_name=phone)


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValidationError(f"密码至少 {MIN_PASSWORD} 位")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError("密码必须同时包含字母和数字")
