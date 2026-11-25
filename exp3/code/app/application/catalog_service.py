"""酒店搜索与房型详情（M6 / M7 的读模型）。

界面只拿这些 ``*Card`` 结构，不再自己拼 SQL：一来 S6-3 禁止界面出现 SQL，
二来"最低价 / 剩余房量"这种聚合必须只有一处口径。

余量口径：区间内**逐日余量的最小值**。一晚卖光就等于整段不可订，这与下单时
``assert_can_occupy`` 的判定一致（它也是逐日都要够）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from app.domain.errors import ValidationError
from app.domain.pricing import stay_dates
from app.infrastructure.db.catalog_query_repository import (
    RoomTypeRow,
    SqliteCatalogQueryRepository,
)
from app.infrastructure.db.inventory_repository import SqliteInventoryRepository


@dataclass(frozen=True, slots=True)
class HotelCard:
    """搜索结果一行。"""

    hotel_id: int
    name: str
    address: str
    phone: str
    room_type_count: int
    min_price_cents: int | None


@dataclass(frozen=True, slots=True)
class RoomTypeCard:  # pylint: disable=too-many-instance-attributes
    """房型详情一行（带最低价与区间剩余量）。

    九个字段全是"界面要显示的东西"（房型名/床型/面积/可住人数/总房量/
    最低价/剩余量），少一个界面就得回头再查一次库。
    """

    room_type_id: int
    hotel_id: int
    name: str
    bed_type: str
    area_sqm: int
    capacity: int
    total_rooms: int
    min_price_cents: int | None
    remaining: int


@dataclass(frozen=True, slots=True)
class HotelDetail:
    """酒店 + 房型列表。"""

    hotel: HotelCard
    room_types: tuple[RoomTypeCard, ...]


class CatalogService:
    """搜索与详情：只读，不改库存也不建单。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._catalog = SqliteCatalogQueryRepository(conn)
        self._inventories = SqliteInventoryRepository(conn)

    def search(
        self, keyword: str | None, check_in_date: date, check_out_date: date
    ) -> list[HotelCard]:
        """按关键词搜酒店，并算出每家的房型数与最低价。"""
        dates = _dates(check_in_date, check_out_date)
        cards: list[HotelCard] = []
        for hotel in self._catalog.search_hotels(keyword):
            rooms = self._catalog.room_types(hotel.hotel_id)
            prices = [self._catalog.min_price_cents(room.room_type_id, dates) for room in rooms]
            known = [price for price in prices if price is not None]
            cards.append(
                HotelCard(
                    hotel_id=hotel.hotel_id,
                    name=hotel.name,
                    address=hotel.address,
                    phone=hotel.phone,
                    room_type_count=len(rooms),
                    min_price_cents=min(known) if known else None,
                )
            )
        return cards

    def detail(
        self, hotel_id: int, check_in_date: date, check_out_date: date
    ) -> HotelDetail | None:
        """酒店详情；酒店不存在或未通过审核时返回 None。"""
        dates = _dates(check_in_date, check_out_date)
        hotel = self._catalog.hotel(hotel_id)
        if hotel is None or hotel.audit_status != "APPROVED":
            return None
        rooms = tuple(
            _room_card(self._catalog, self._inventories, row, dates)
            for row in self._catalog.room_types(hotel_id)
        )
        prices = [card.min_price_cents for card in rooms if card.min_price_cents is not None]
        card = HotelCard(
            hotel_id=hotel.hotel_id,
            name=hotel.name,
            address=hotel.address,
            phone=hotel.phone,
            room_type_count=len(rooms),
            min_price_cents=min(prices) if prices else None,
        )
        return HotelDetail(hotel=card, room_types=rooms)


def _room_card(
    catalog: SqliteCatalogQueryRepository,
    inventories: SqliteInventoryRepository,
    row: RoomTypeRow,
    dates: list[date],
) -> RoomTypeCard:
    remaining = min(inventories.range_remaining(row.room_type_id, dates).values(), default=0)
    return RoomTypeCard(
        room_type_id=row.room_type_id,
        hotel_id=row.hotel_id,
        name=row.name,
        bed_type=row.bed_type,
        area_sqm=row.area_sqm,
        capacity=row.capacity,
        total_rooms=row.total_rooms,
        min_price_cents=catalog.min_price_cents(row.room_type_id, dates),
        remaining=remaining,
    )


def _dates(check_in_date: date, check_out_date: date) -> list[date]:
    if check_out_date <= check_in_date:
        raise ValidationError("退房日期必须晚于入住日期")
    return stay_dates(check_in_date, check_out_date)
