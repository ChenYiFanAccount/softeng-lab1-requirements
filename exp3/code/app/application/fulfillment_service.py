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
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

#: ``settings.json`` 未配 ``runtime.timezone`` 时按本地时区（课程场景固定为 Asia/Shanghai）
DEFAULT_TIMEZONE = "Asia/Shanghai"

#: Windows 上 ``zoneinfo`` 需要 tzdata 包；缺失时退化为固定偏移。
#: Asia/Shanghai 不实行夏令时，+08:00 与 ZoneInfo 结果完全等价。
FALLBACK_TIMEZONE = timezone(timedelta(hours=8))

#: 不需要 tz 数据库就能确定的时区名（Windows 上常常没有 tzdata）
FIXED_TIMEZONES: dict[str, tzinfo] = {
    "UTC": timezone.utc,
    "ETC/UTC": timezone.utc,
    "GMT": timezone.utc,
    "Z": timezone.utc,
    "ASIA/SHANGHAI": FALLBACK_TIMEZONE,
    "PRC": FALLBACK_TIMEZONE,
}


@dataclass(slots=True)
class ScanReport:
    """一次扫描的结果，供调度工具打印与审计核对。"""

    scanned_at: datetime
    timeouts: int = 0
    auto_check_ins: int = 0
    no_shows: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    timezone_name: str = DEFAULT_TIMEZONE

    @property
    def total(self) -> int:
        """本次扫描实际改动的订单数（不含失败）。"""
        return self.timeouts + self.auto_check_ins + self.no_shows

    def to_dict(self) -> dict[str, Any]:
        """扁平字典，便于打印或写日志。

        ``scanned_at`` 是**规范时刻（UTC）**，写日志与比对用；``scanned_at_local``
        是按配置时区换算的墙钟时间，给人看——两者都打印，避免再出现
        "日志里 13:05、本地 21:05" 的误读（S4-R1-01）。
        """
        return {
            "scanned_at": _utc_of(self.scanned_at).strftime("%Y-%m-%d %H:%M:%S"),
            "scanned_at_local": _utc_of(self.scanned_at)
            .astimezone(load_timezone(self.timezone_name))
            .strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": self.timezone_name,
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
        report = ScanReport(scanned_at=self._clock.now(), timezone_name=self.timezone_name)
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

    # ------------------------------------------------------------------ 时区换算

    @property
    def timezone_name(self) -> str:
        """配置时区（``runtime.timezone``），no-show 的 ``23:59`` 指**当地墙钟**。"""
        runtime = self._settings.get("runtime")
        name = runtime.get("timezone") if isinstance(runtime, dict) else None
        return str(name or DEFAULT_TIMEZONE)

    def _utc(self, moment: datetime) -> datetime:
        """把时钟给的时刻规范成 UTC（朴素时间按 UTC 解释，去掉 tzinfo 便于写库）。"""
        return _utc_of(moment).replace(tzinfo=None)

    def _local(self, moment: datetime) -> datetime:
        """UTC 时刻 → 配置时区的墙钟时间。"""
        return _utc_of(moment).astimezone(load_timezone(self.timezone_name))

    # ------------------------------------------------------------------ 三条规则

    def _scan_timeouts(self, report: ScanReport) -> None:
        """规则一：待确认超时 → T3 取消并回补库存。

        ``created_at`` 落库是 UTC，故截止时刻也在 UTC 上算，与展示时区无关。
        """
        cutoff = self._utc(self._clock.now()) - timedelta(minutes=self.timeout_minutes)
        pending = self._bookings.list_pending_created_before(cutoff, self.batch_limit)
        for booking in pending:
            if self._apply(booking.booking_no, BookingEvent.TIMEOUT, report):
                report.timeouts += 1

    def _scan_auto_check_ins(self, report: ScanReport) -> None:
        """规则二：已确认但入住日已过 → T5 自动入住。

        ``check_in_date`` 是**当地日历日**，所以"今天"必须用本地墙钟取，不能用 UTC 日期
        （UTC 日期在北京时间 08:00 前还是前一天）。
        """
        today = self._local(self._clock.now()).date()
        confirmed = self._bookings.list_confirmed_check_in_before(today, self.batch_limit)
        for booking in confirmed:
            if self._apply(booking.booking_no, BookingEvent.AUTO_CHECK_IN, report):
                report.auto_check_ins += 1

    def _scan_no_shows(self, report: ScanReport) -> None:
        """规则三：入住日当天过 cutoff 仍未入住 → T7 no-show。

        cutoff 是**当地墙钟**（默认 23:59，即 ≥ 23:59:00 就触发）。时钟返回 UTC，
        所以先换算到配置时区再取日期与时刻，否则真实运行时会在当地次日 07:59
        才判 no-show（S4-R1-01 修的就是这条）。
        """
        local_now = self._local(self._clock.now())
        if local_now.time() < _parse_clock(self.no_show_cutoff):
            return
        confirmed = self._bookings.list_confirmed_check_in_on(local_now.date(), self.batch_limit)
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


def _utc_of(moment: datetime) -> datetime:
    """把任意时刻规范成带 UTC 时区的 ``datetime``。

    ``SystemClock``/``FrozenClock`` 给的都可能是朴素时间，约定按 UTC 解释；
    带时区的则原样换算。统一在这里做，调用点不用各写一遍 ``tzinfo`` 判断。
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def load_timezone(name: str) -> tzinfo:
    """按 IANA 名称取时区；没有 tz 数据库时退化为固定偏移。

    先查 ``FIXED_TIMEZONES``（``UTC``、``Asia/Shanghai`` 这类无夏令时的常用值），
    再交给 ``ZoneInfo``；两者都不成时按 +08:00 处理——课程场景只涉及中国，
    退化的结果与 ``Asia/Shanghai`` 逐秒一致，不会静默算错。

    Args:
        name: 形如 ``"Asia/Shanghai"`` 的时区名。

    Returns:
        可用于 ``astimezone`` 的 ``tzinfo``。
    """
    key = name.strip().upper()
    fixed = FIXED_TIMEZONES.get(key)
    if fixed is not None:
        return fixed
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return FALLBACK_TIMEZONE
