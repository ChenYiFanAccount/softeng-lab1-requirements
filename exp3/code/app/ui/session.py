"""界面会话：持有连接、当前操作者与跨屏上下文。

三个职责：
1. 登录 / 登出（认人、验密码、拦停用账号）；
2. 懒建应用服务（界面只拿服务，不拿仓储，更不拿 SQL —— S6-3）；
3. 跨屏上下文（搜了哪家酒店、选了哪个房型、看哪张单），屏幕之间不互相引用。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from app.application.actor import Actor
from app.application.account_service import AccountService
from app.application.admin_service import AdminService
from app.application.audit_service import AuditService
from app.application.booking_service import BookingAppService
from app.application.catalog_service import CatalogService
from app.application.clock import Clock, SystemClock
from app.application.inventory_service import InventoryAppService
from app.application.reconcile_service import ReconcileService
from app.application.report_service import ReportService
from app.domain.enums import ActorRole
from app.domain.errors import DomainError, PermissionDeniedError
from app.infrastructure.db.catalog_repository import SqliteAccountRepository
from app.infrastructure.security import verify_password

DISABLED_MESSAGE = "账号已停用，请联系平台管理员"


@dataclass
class Session:
    """一次登录会话；``actor`` 为空表示未登录。"""

    conn: sqlite3.Connection
    clock: Clock = field(default_factory=SystemClock)
    actor: Actor | None = None
    context: dict[str, Any] = field(default_factory=dict)
    _services: dict[str, Any] = field(default_factory=dict, repr=False)

    # ── 登录 ──────────────────────────────────────────────────────────
    def login(self, login_name: str, password: str) -> Actor:
        """按手机号登录；密码错、账号不存在、已停用都抛 ``DomainError``。"""
        account = SqliteAccountRepository(self.conn).find_by_login((login_name or "").strip())
        if account is None:
            raise DomainError("手机号或密码不正确")
        if not verify_password(password, str(account["password_hash"])):
            raise DomainError("手机号或密码不正确")
        if account["status"] != "ACTIVE":
            raise DomainError(DISABLED_MESSAGE)
        self.actor = Actor(
            account_id=int(account["id"]),
            role=ActorRole(str(account["role"])),
            hotel_id=None if account["hotel_id"] is None else int(account["hotel_id"]),
            login_name=str(account["login_name"]),
        )
        self.context.clear()
        return self.actor

    def logout(self) -> None:
        """登出并清空上下文与缓建的服务。"""
        self.actor = None
        self.context.clear()
        self._services.clear()

    def require_actor(self) -> Actor:
        """取当前操作者；未登录抛 403（界面在 ``on_show`` 里兜住并提示）。"""
        if self.actor is None:
            raise PermissionDeniedError("请先登录")
        return self.actor

    # ── 上下文 ────────────────────────────────────────────────────────
    def remember(self, **values: Any) -> None:
        """记住跨屏选择（入住日、酒店、房型、订单号……）。"""
        self.context.update(values)

    def recall(self, key: str, default: Any = None) -> Any:
        """取跨屏上下文。"""
        return self.context.get(key, default)

    # ── 服务 ──────────────────────────────────────────────────────────
    def bookings(self) -> BookingAppService:
        """下单 / 取消 / 改期 / 办理（M1、M4、M5）。"""
        return self._service("bookings", lambda: BookingAppService(self.conn, clock=self.clock))

    def inventory(self) -> InventoryAppService:
        """库存与销售状态维护（M2）。"""
        return self._service("inventory", lambda: InventoryAppService(self.conn, clock=self.clock))

    def catalog(self) -> CatalogService:
        """搜索与详情（M6、M7）。"""
        return self._service("catalog", lambda: CatalogService(self.conn))

    def reports(self) -> ReportService:
        """统计报表（M8）。"""
        return self._service("reports", lambda: ReportService(self.conn))

    def reconcile(self) -> ReconcileService:
        """对账（M10）；界面"立即对账"必须走这里（D-025 第 5 条）。"""
        return self._service("reconcile", lambda: ReconcileService(self.conn))

    def accounts(self) -> AccountService:
        """注册（M9 顾客侧）。"""
        return self._service("accounts", lambda: AccountService(self.conn))

    def audit(self) -> AuditService:
        """审计查询（只读）。"""
        return self._service("audit", lambda: AuditService(self.conn))

    def admin(self) -> AdminService:
        """平台管理（M9）。"""
        return self._service("admin", lambda: AdminService(self.conn, clock=self.clock))

    def _service(self, key: str, factory: Any) -> Any:
        if key not in self._services:
            self._services[key] = factory()
        return self._services[key]
