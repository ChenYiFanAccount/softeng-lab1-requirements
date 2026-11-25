"""行 ↔ 领域对象的取值换算（集中一处，别在每个仓储里重复）。

约定（与 `0001_init.sql` 头注释一致）：

- 日期：``TEXT 'YYYY-MM-DD'``，SQLite 下可直接比较大小；
- 时间：``TEXT 'YYYY-MM-DD HH:MM:SS'``（UTC，秒级，丢掉微秒以保持一致）；
- 金额：``INTEGER`` 分；
- 枚举：大写英文码，领域层用 ``StrEnum`` 承载。
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def date_text(value: date) -> str:
    """日期 → 库里的 ISO 文本。"""
    return value.isoformat()


def parse_date(value: str | None) -> date | None:
    """库里的 ISO 文本 → 日期；空值返回 None。"""
    if not value:
        return None
    return date.fromisoformat(str(value))


def time_text(value: datetime | None) -> str:
    """时间 → 库里的 UTC 文本（秒级，去微秒）。"""
    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def parse_time(value: str | None) -> datetime | None:
    """库里的 UTC 文本 → 带时区的时间；空值返回 None。"""
    if not value:
        return None
    text = str(value)
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(text, pattern)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc)
    return None
