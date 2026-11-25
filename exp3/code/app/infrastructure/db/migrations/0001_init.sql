-- 0001_init.sql —— 12 张表的初始结构（对应 exp2/设计基线/03_数据设计.md §2）
-- 约定：日期用 TEXT 'YYYY-MM-DD'（SQLite 下 ISO 文本可直接比较大小），
--       时间用 TEXT 'YYYY-MM-DD HH:MM:SS'（UTC），金额用 INTEGER 分（禁止浮点）。
--       枚举一律用 TEXT + CHECK，取值为大写英文码，界面负责中英映射。

CREATE TABLE hotel (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,                  -- U2 酒店名称唯一
    address       TEXT    NOT NULL,
    phone         TEXT    NOT NULL,
    description   TEXT,
    audit_status  TEXT    NOT NULL DEFAULT 'PENDING'
                  CHECK (audit_status IN ('PENDING', 'APPROVED', 'REJECTED')),
    reject_reason TEXT,
    created_at    TEXT    NOT NULL,
    audited_at    TEXT,
    CHECK (audit_status <> 'REJECTED' OR reject_reason IS NOT NULL)
);

CREATE TABLE user_account (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    login_name    TEXT    NOT NULL UNIQUE,                  -- U1 手机号唯一
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL
                  CHECK (role IN ('CUSTOMER', 'HOTEL_STAFF', 'PLATFORM_ADMIN')),
    hotel_id      INTEGER REFERENCES hotel (id),            -- 仅酒店工作人员有值
    status        TEXT    NOT NULL DEFAULT 'ACTIVE'
                  CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at    TEXT    NOT NULL,
    CHECK ((role = 'HOTEL_STAFF') = (hotel_id IS NOT NULL))
);

CREATE TABLE room_type (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotel_id    INTEGER NOT NULL REFERENCES hotel (id),
    name        TEXT    NOT NULL,
    bed_type    TEXT    NOT NULL,
    area_sqm    INTEGER NOT NULL CHECK (area_sqm > 0),
    capacity    INTEGER NOT NULL CHECK (capacity > 0),
    total_rooms INTEGER NOT NULL CHECK (total_rooms > 0),
    UNIQUE (hotel_id, name)                                 -- U3 同酒店内房型名唯一
);

CREATE TABLE room_inventory (
    room_type_id   INTEGER NOT NULL REFERENCES room_type (id),
    stay_date      TEXT    NOT NULL,                        -- 'YYYY-MM-DD'
    available_rooms INTEGER NOT NULL CHECK (available_rooms >= 0),
    occupied_rooms  INTEGER NOT NULL DEFAULT 0 CHECK (occupied_rooms >= 0),
    sale_status    TEXT    NOT NULL DEFAULT 'ON_SALE'
                   CHECK (sale_status IN ('ON_SALE', 'SUSPENDED')),
    updated_at     TEXT    NOT NULL,
    PRIMARY KEY (room_type_id, stay_date),                  -- U4 房型 × 日期唯一
    CHECK (occupied_rooms <= available_rooms)               -- 行内区间约束
);

CREATE TABLE room_price (
    room_type_id     INTEGER NOT NULL REFERENCES room_type (id),
    stay_date        TEXT    NOT NULL,
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents > 0),
    updated_at       TEXT    NOT NULL,
    PRIMARY KEY (room_type_id, stay_date)                   -- U5 房型 × 日期唯一
);

CREATE TABLE idempotency_key (
    key_value  TEXT PRIMARY KEY,                            -- T2 幂等键唯一
    booking_no TEXT,                                        -- 弱引用，避免与 booking 成环
    created_at TEXT NOT NULL
);

CREATE TABLE booking (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_no        TEXT    NOT NULL UNIQUE,              -- T1 订单号唯一
    guest_id          INTEGER NOT NULL REFERENCES user_account (id),
    hotel_id          INTEGER NOT NULL REFERENCES hotel (id),
    room_type_id      INTEGER NOT NULL REFERENCES room_type (id),
    room_count        INTEGER NOT NULL CHECK (room_count > 0),
    check_in_date     TEXT    NOT NULL,
    check_out_date    TEXT    NOT NULL,
    total_price_cents INTEGER NOT NULL CHECK (total_price_cents >= 0),
    status            TEXT    NOT NULL
                      CHECK (status IN ('PENDING', 'CONFIRMED', 'CHECKED_IN',
                                        'CHECKED_OUT', 'CANCELLED', 'NO_SHOW')),
    idempotency_key   TEXT REFERENCES idempotency_key (key_value),
    cancel_reason     TEXT,
    cancel_initiator  TEXT
                      CHECK (cancel_initiator IN ('CUSTOMER', 'HOTEL', 'SYSTEM', 'ADMIN')),
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    CHECK (check_out_date > check_in_date)                  -- 退房日必须晚于入住日
);

-- U6：同一顾客 + 同酒店 + 同房型 + 同时段，在有效状态内最多一单。
-- 只拦「起止日完全相同」的重复；日期重叠但不相同的单必须由应用层在
-- BEGIN IMMEDIATE 事务内按「房型 × 日期」复核（见 03_数据设计.md §9.1 边界）。
CREATE UNIQUE INDEX ux_booking_active_period
    ON booking (guest_id, hotel_id, room_type_id, check_in_date, check_out_date)
    WHERE status IN ('PENDING', 'CONFIRMED', 'CHECKED_IN');

CREATE INDEX ix_booking_guest ON booking (guest_id, created_at);
CREATE INDEX ix_booking_hotel ON booking (hotel_id, check_in_date);
CREATE INDEX ix_booking_status ON booking (status, created_at);

CREATE TABLE booking_night (
    booking_id       INTEGER NOT NULL REFERENCES booking (id) ON DELETE CASCADE,
    stay_date        TEXT    NOT NULL,
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents > 0),
    room_count       INTEGER NOT NULL CHECK (room_count > 0),
    PRIMARY KEY (booking_id, stay_date)                     -- T3 订单 × 晚唯一
);

CREATE TABLE stay_record (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id  INTEGER NOT NULL REFERENCES booking (id),
    action      TEXT    NOT NULL CHECK (action IN ('CHECK_IN', 'CHECK_OUT', 'NO_SHOW')),
    operator_id INTEGER NOT NULL REFERENCES user_account (id),
    source      TEXT    NOT NULL CHECK (source IN ('MANUAL', 'SYSTEM')),
    remark      TEXT,
    created_at  TEXT    NOT NULL
);

-- 审计日志只追加：不建外键，避免主表记录清理时连带破坏历史（弱引用）。
CREATE TABLE audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id   INTEGER NOT NULL,
    operator_role TEXT    NOT NULL,
    target_type   TEXT    NOT NULL,
    target_id     TEXT    NOT NULL,
    action        TEXT    NOT NULL,
    before_state  TEXT,
    after_state   TEXT,
    created_at    TEXT    NOT NULL
);

CREATE INDEX ix_audit_target ON audit_log (target_type, target_id, created_at);
CREATE INDEX ix_audit_created ON audit_log (created_at);

CREATE TABLE notification_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id      INTEGER NOT NULL REFERENCES booking (id),
    channel         TEXT    NOT NULL CHECK (channel IN ('IN_APP', 'SMS')),
    content_summary TEXT    NOT NULL,
    result          TEXT    NOT NULL DEFAULT 'PENDING_NEGOTIATION'
                    CHECK (result IN ('PENDING_NEGOTIATION', 'ACCEPTED',
                                      'REJECTED', 'RESCHEDULED')),
    notified_at     TEXT    NOT NULL
);

CREATE TABLE holiday_calendar (
    holiday_date TEXT PRIMARY KEY,                          -- T4 节假日日期唯一
    name         TEXT,
    status       TEXT NOT NULL DEFAULT 'ENABLED'
                 CHECK (status IN ('ENABLED', 'DISABLED'))
);
