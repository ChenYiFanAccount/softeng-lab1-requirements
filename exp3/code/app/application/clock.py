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
class Clock(Protocol):  # pylint: disable=too-few-public-methods
    """时钟协议：只要提供一个无参 ``now()`` 就能被业务层接受。

    协议就该只有一个方法——业务层真正需要的只是"现在几点"，多一个方法
    就多一份实现负担（这也是不用抽象基类而用 Protocol 的原因）。
    """

    def now(self) -> datetime:
        """返回当前时间。"""
        ...


@dataclass(slots=True)
class SystemClock:
    """真实时钟：生产运行与界面使用。"""

    def now(self) -> datetime:
        """返回系统当前 UTC 时间。"""
        return utc_now()


@dataclass(slots=True)
class FrozenClock:
    """可拨动的假时钟：用例里用它一步跨过等待时间，不必真等。"""

    current: datetime = field(default_factory=utc_now)

    def now(self) -> datetime:
        """返回被冻结（或被拨动后）的时间。"""
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        """向前拨动时间，返回拨动后的值。"""
        self.current = self.current + delta
        return self.current

    def set(self, moment: datetime) -> datetime:
        """直接设定到某一时刻（用于跨零点用例）。"""
        self.current = moment
        return self.current
