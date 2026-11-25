"""领域层公开面：13 个核心类型（12 实体 + 1 枚举）、3 个服务、3 个仓储接口。

上层（应用层 / 界面层）只允许 ``from app.domain import X`` 这种方式取用，
不直接摸子模块路径，便于日后重排文件而不动调用方。
"""

from __future__ import annotations

from app.domain.enums import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    ActorRole,
    BookingEvent,
    BookingStatus,
)
from app.domain.errors import (
    DomainError,
    DuplicateBookingError,
    IllegalTransitionError,
    InvalidStateError,
    NoAvailabilityError,
    PermissionDeniedError,
    ValidationError,
)
from app.domain.inventory import (
    OccupancyPlan,
    assert_can_occupy,
    plan_occupancy,
    range_limit_message,
    range_remaining,
)
from app.domain.models import (
    AuditLog,
    Booking,
    BookingNight,
    HolidayCalendar,
    Hotel,
    IdempotencyKey,
    NotificationRecord,
    RoomInventory,
    RoomPrice,
    RoomType,
    StayRecord,
    UserAccount,
)
from app.domain.pricing import Quote, quote, stay_dates, total_from_nights
from app.domain.repositories import (
    AuditLogRepository,
    BookingRepository,
    InventoryRepository,
)
from app.domain.services import BookingService, InventoryService
from app.domain.state_machine import (
    FORBIDDEN_TRANSITIONS,
    TRANSITIONS,
    BookingStateMachine,
    Transition,
)

__all__ = [
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "FORBIDDEN_TRANSITIONS",
    "TRANSITIONS",
    "ActorRole",
    "AuditLog",
    "AuditLogRepository",
    "Booking",
    "BookingEvent",
    "BookingNight",
    "BookingRepository",
    "BookingService",
    "BookingStateMachine",
    "BookingStatus",
    "DomainError",
    "DuplicateBookingError",
    "HolidayCalendar",
    "Hotel",
    "IdempotencyKey",
    "IllegalTransitionError",
    "InvalidStateError",
    "InventoryRepository",
    "InventoryService",
    "NoAvailabilityError",
    "NotificationRecord",
    "OccupancyPlan",
    "PermissionDeniedError",
    "Quote",
    "RoomInventory",
    "RoomPrice",
    "RoomType",
    "StayRecord",
    "Transition",
    "UserAccount",
    "ValidationError",
    "assert_can_occupy",
    "plan_occupancy",
    "quote",
    "range_limit_message",
    "range_remaining",
    "stay_dates",
    "total_from_nights",
]
