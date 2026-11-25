"""应用层入参（命令对象）。

命令对象只承载"调用者给的东西"，不做校验——校验发生在应用服务里，因为
同一条命令在用假时钟、不同角色下会有不同的判定结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PlaceBookingCommand:  # pylint: disable=too-many-instance-attributes
    """下单命令：顾客 + 房型 + 起止日 + 间数，可选幂等键。

    八个字段全部来自"下单表单"，少一个就下不了单，因此不合并、也不给
    "默认酒店"之类的暗默认值。
    """

    guest_id: int
    hotel_id: int
    room_type_id: int
    check_in_date: date
    check_out_date: date
    room_count: int = 1
    idempotency_key: str | None = None
    remark: str | None = None


@dataclass(frozen=True, slots=True)
class RescheduleCommand:
    """改期命令：只带新日期区间，其余信息从原订单取。"""

    new_check_in_date: date
    new_check_out_date: date
    reason: str | None = None
