"""操作者身份（应用层入参）。

数据库里角色是 ``CUSTOMER`` / ``HOTEL_STAFF`` / ``PLATFORM_ADMIN``，而订单表的
``cancel_initiator`` 只允许 ``CUSTOMER`` / ``HOTEL`` / ``ADMIN`` / ``SYSTEM``
（见 ``0001_init.sql`` 的 CHECK）。两套词表只在本模块换算一次，别处不要再写映射。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.enums import SYSTEM_ACCOUNT_ID, ActorRole

#: 角色 → 订单表 ``cancel_initiator`` 取值
INITIATOR_BY_ROLE: dict[ActorRole, str] = {
    ActorRole.CUSTOMER: "CUSTOMER",
    ActorRole.HOTEL_STAFF: "HOTEL",
    ActorRole.PLATFORM_ADMIN: "ADMIN",
    ActorRole.SYSTEM: "SYSTEM",
}


@dataclass(frozen=True, slots=True)
class Actor:
    """一次操作的操作者：账号、角色，以及（酒店员工才有的）所属酒店。"""

    account_id: int
    role: ActorRole
    hotel_id: int | None = None
    login_name: str = ""

    @property
    def is_admin(self) -> bool:
        """是否平台管理员（跨酒店）。"""
        return self.role is ActorRole.PLATFORM_ADMIN

    @property
    def is_system(self) -> bool:
        """是否系统自动动作（超时扫描、自动入住）。"""
        return self.role is ActorRole.SYSTEM

    @property
    def initiator_code(self) -> str:
        """订单表 ``cancel_initiator`` 列要的值。"""
        return INITIATOR_BY_ROLE[self.role]

    def works_at(self, hotel_id: int) -> bool:
        """是否在本酒店任职。"""
        return self.role is ActorRole.HOTEL_STAFF and self.hotel_id == hotel_id

    @classmethod
    def from_row(cls, row: Any) -> "Actor":
        """从 ``user_account`` 行构造（``sqlite3.Row`` 或任意支持按名取值的对象）。"""
        return cls(
            account_id=int(row["id"]),
            role=ActorRole(str(row["role"])),
            hotel_id=None if row["hotel_id"] is None else int(row["hotel_id"]),
            login_name=str(row["login_name"]),
        )

    @classmethod
    def system(cls) -> "Actor":
        """系统动作的伪操作者（用于超时取消、自动入住、no-show）。

        ``account_id`` 取 :data:`app.domain.enums.SYSTEM_ACCOUNT_ID`——种子数据里确有
        这一行"系统服务账号"（登录名 ``system``、口令不可用），因此写 ``stay_record``
        时外键成立；``audit_log`` 无外键，记的也是同一个 id。
        """
        return cls(
            account_id=SYSTEM_ACCOUNT_ID,
            role=ActorRole.SYSTEM,
            hotel_id=None,
            login_name="system",
        )
