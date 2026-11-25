"""应用层：事务边界、权限、幂等与用例编排。

模块划分（一模块一文件，对应 `02_模块划分与交互.md` 的 M1–M5 纵切）：

- ``booking_service``：M1 下单、M4 取消、M5 改期；
- ``inventory_service``：M2 库存维护（调可售、停售、复售）；
- ``commands``：用例入参（不可变）；
- ``actor``：调用者身份与角色；
- ``clock``：可注入时钟（测试用 ``FrozenClock`` 钉住时间）；
- ``errors``：应用层错误（含"不泄露存在性"的统一 403 文案）。
"""

from app.application.actor import Actor
from app.application.booking_service import BookingAppService
from app.application.clock import Clock, FrozenClock, SystemClock, utc_now
from app.application.commands import PlaceBookingCommand, RescheduleCommand
from app.application.errors import (
    MASKED_BOOKING_MESSAGE,
    ConflictError,
    bad_request,
    masked_booking_error,
)
from app.application.inventory_service import InventoryAppService

__all__ = [
    "MASKED_BOOKING_MESSAGE",
    "Actor",
    "BookingAppService",
    "Clock",
    "ConflictError",
    "FrozenClock",
    "InventoryAppService",
    "PlaceBookingCommand",
    "RescheduleCommand",
    "SystemClock",
    "bad_request",
    "masked_booking_error",
    "utc_now",
]
