"""可注入时钟。

超时取消、no-show 判定、审计时间戳一律走这里，**禁止**在业务代码里散落
``datetime.now()``——否则 S4 的假时钟用例没法把时间拨到 23:59 前后。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable


def utc_now() -> datetime:
    """返回带时区的当前 UTC 时间（全库统一存 UTC）。"""
    return datetime.now(timezone.utc)


@runtime_checkable
class Clock(Protocol):
    """时钟协议：``now()`` 给时间，``source()`` 说明时间从哪来。

    ``source()`` 不是装饰：审计与扫描报告里要写清"这条时间是真实时钟还是
    用例拨动的假时钟"，否则现场看到一条 2026-11-25 的记录，没人能判断它是
    真发生过的还是回归用例造出来的。
    """

    def now(self) -> datetime:
        """返回当前时间。"""
        ...

    def source(self) -> str:
        """返回时间来源标签（``system`` / ``frozen``）。"""
        ...


@dataclass(slots=True)
class SystemClock:
    """真实时钟：生产运行与界面使用。"""

    def now(self) -> datetime:
        """返回系统当前 UTC 时间。"""
        return utc_now()

    def source(self) -> str:
        """真实时钟的来源标签。"""
        return "system"


@dataclass(slots=True)
class FrozenClock:
    """可拨动的假时钟：用例里用它一步跨过等待时间，不必真等。"""

    current: datetime = field(default_factory=utc_now)

    def now(self) -> datetime:
        """返回被冻结（或被拨动后）的时间。"""
        return self.current

    def source(self) -> str:
        """假时钟的来源标签。"""
        return "frozen"

    def advance(self, delta: timedelta) -> datetime:
        """向前拨动时间，返回拨动后的值。"""
        self.current = self.current + delta
        return self.current

    def set(self, moment: datetime) -> datetime:
        """直接设定到某一时刻（用于跨零点用例）。"""
        self.current = moment
        return self.current
