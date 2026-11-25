"""履约调度（M3）：把"时间到了就该发生的事"从 HTTP 请求里剥出来。

三条调度规则（对应 `exp2/设计基线/02_模块划分与交互.md` M3 与 exp1 的 T3/T5/T7）：

1. **超时取消**：``PENDING`` 单建单超过 ``pending_timeout_minutes`` 分钟仍无人处理，
   系统按 T3 取消并回补库存。
2. **自动入住**：``CONFIRMED`` 单入住日已过，系统按 T5 补记入住（酒店忘了点"办理入住"
   时的兜底，避免订单永远停在已确认）。
3. **当日 no-show**：``CONFIRMED`` 单入住日正是今天且已过 ``no_show_cutoff``
   （默认 23:59），系统按 T7 记未入住并释放当天及之后的占用。

**时钟必须可注入**（S4-1 的硬要求）。本模块只读 ``Clock.now()``，绝不 ``sleep``、
绝不 ``datetime.now()``——测试用 ``FrozenClock`` 把"三天后"一步拨过去，整套扫描
在毫秒级跑完。后台调度器（``code/tools/scan_once.py``）同样只调用本模块，自己
不判断时间。

扫描是**幂等**的：每条规则都只挑"当前状态仍符合条件"的订单，第一次扫描把状态
改掉之后，第二次扫描的查询自然查不到它们，因此不会重复回补库存（S4-2）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import Clock, SystemClock
from app.domain.enums import BookingEvent
from app.domain.errors import DomainError
from app.infrastructure.db.booking_repository import SqliteBookingRepository

#: ``settings.json`` 缺 ``fulfillment`` 块时的兜底，与配置文件保持一致
DEFAULT_TIMEOUT_MINUTES = 30
DEFAULT_NO_SHOW_CUTOFF = "23:59"
DEFAULT_BATCH_LIMIT = 200


@dataclass(slots=True)
class ScanReport:
    """一次扫描的结果，供调度工具打印与审计核对。"""

    scanned_at: datetime
    timeouts: int = 0
    auto_check_ins: int = 0
    no_shows: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """本次扫描实际改动的订单数（不含失败）。"""
        return self.timeouts + self.auto_check_ins + self.no_shows

    def to_dict(self) -> dict[str, Any]:
        """扁平字典，便于打印或写日志。"""
        return {
            "scanned_at": self.scanned_at.strftime("%Y-%m-%d %H:%M:%S"),
            "timeouts": self.timeouts,
            "auto_check_ins": self.auto_check_ins,
            "no_shows": self.no_shows,
            "failures": len(self.failures),
            "total": self.total,
        }


class FulfillmentService:
    """按当前时刻推进订单状态（超时取消、自动入住、no-show）。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        clock: Clock | None = None,
        settings: dict[str, Any] | None = None,
        booking_service: BookingAppService | None = None,
    ) -> None:
        """装配扫描服务。

        Args:
            conn: 已按工厂建好、PRAGMA 齐全的连接（每线程独立）。
            clock: 可注入时钟；省略时用 ``SystemClock()``（真实时间）。
            settings: 完整配置字典；只读取其中的 ``fulfillment`` 块。
            booking_service: 复用已有应用服务（主要给测试注入假时钟用）；省略时自建。
        """
        self._conn = conn
        self._clock: Clock = clock or SystemClock()
        self._settings = settings or {}
        self._booking_service = booking_service or BookingAppService(conn, clock=self._clock)
        self._bookings = SqliteBookingRepository(conn)
        self._system = Actor.system()

    # ------------------------------------------------------------------ 对外入口

    def scan_once(self) -> ScanReport:
        """跑一轮完整扫描（三条规则各一次），返回统计。"""
        report = ScanReport(scanned_at=self._clock.now())
        self._scan_timeouts(report)
        if self._auto_check_in_enabled:
            self._scan_auto_check_ins(report)
        self._scan_no_shows(report)
        return report

    # ------------------------------------------------------------------ 配置读取

    @property
    def _options(self) -> dict[str, Any]:
        block = self._settings.get("fulfillment")
        return block if isinstance(block, dict) else {}

    @property
    def timeout_minutes(self) -> int:
        """待确认单的存活分钟数。"""
        value = self._options.get("pending_timeout_minutes", DEFAULT_TIMEOUT_MINUTES)
        return int(value)

    @property
    def no_show_cutoff(self) -> str:
        """当日 no-show 判定时刻（``HH:MM``）。"""
        value = str(self._options.get("no_show_cutoff", DEFAULT_NO_SHOW_CUTOFF))
        return value

    @property
    def batch_limit(self) -> int:
        """单条规则每轮最多处理多少张单（防止一次扫描把库拖住）。"""
        return int(self._options.get("batch_limit", DEFAULT_BATCH_LIMIT))

    @property
    def _auto_check_in_enabled(self) -> bool:
        return bool(self._options.get("auto_check_in_enabled", True))

    # ------------------------------------------------------------------ 三条规则

    def _scan_timeouts(self, report: ScanReport) -> None:
        """规则一：待确认超时 → T3 取消并回补库存。"""
        cutoff = self._clock.now() - timedelta(minutes=self.timeout_minutes)
        pending = self._bookings.list_pending_created_before(cutoff, self.batch_limit)
        for booking in pending:
            if self._apply(booking.booking_no, BookingEvent.TIMEOUT, report):
                report.timeouts += 1

    def _scan_auto_check_ins(self, report: ScanReport) -> None:
        """规则二：已确认但入住日已过 → T5 自动入住。"""
        today = self._clock.now().date()
        confirmed = self._bookings.list_confirmed_check_in_before(today, self.batch_limit)
        for booking in confirmed:
            if self._apply(booking.booking_no, BookingEvent.AUTO_CHECK_IN, report):
                report.auto_check_ins += 1

    def _scan_no_shows(self, report: ScanReport) -> None:
        """规则三：入住日当天过 cutoff 仍未入住 → T7 no-show。"""
        now = self._clock.now()
        if now.time() < _parse_clock(self.no_show_cutoff):
            return
        confirmed = self._bookings.list_confirmed_check_in_on(now.date(), self.batch_limit)
        for booking in confirmed:
            if self._apply(booking.booking_no, BookingEvent.NO_SHOW, report):
                report.no_shows += 1

    # ------------------------------------------------------------------ 单条推进

    def _apply(self, booking_no: str, event: BookingEvent, report: ScanReport) -> bool:
        """对一张单执行一次系统事件；成功返回 True，被规则拒则记入 failures。"""
        try:
            self._booking_service.apply_event(booking_no, event, self._system, reason="SYSTEM_SCAN")
        except DomainError as error:
            report.failures.append(
                {
                    "booking_no": booking_no,
                    "event": event.value,
                    "code": error.code,
                    "message": str(error),
                }
            )
            return False
        return True


def _parse_clock(text: str) -> time:
    """把 ``"23:59"`` 解析成 ``datetime.time``（非法输入直接抛 ValueError）。"""
    parts = text.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"no_show_cutoff 必须是 HH:MM：{text!r}")
    return time(int(parts[0]), int(parts[1]))
