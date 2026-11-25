# 类图未覆盖的实现符号（14 个）

类图（`exp2/UML/UML类图.puml` v1.1）登记了 19 个符号，`check_uml_sync.py` 双向比对为 0 缺失；
但 `code/app` 里另有 14 个类/枚举是**实现层新增**、类图未画。它们不改变设计语义，只是把
类图里的"箭头与约束"落成可执行对象。报告差异表引用本文件即可。

## 3 个代表符号

| 符号 | 用途 | 为什么类图里没有 |
|---|---|---|
| `Quote` | 报价结果值对象：总价（整数分）、晚数、均价，以及转成 `BookingNight` 列表的方法 | 类图只画了 `RoomPrice`（单价）与 `Booking`（总价），"算价中间结果"属实现细节 |
| `Transition` | 状态机一条边的不可变描述：编号（T1–T8）、事件、源/目标状态、允许角色、触发者类型 | 类图用 `BookingStateMachine` 一个类概括了整张转移表，没把"边"建模成对象 |
| `SeedOutcome` | 种子装载结果：是否实际写入、各表行数快照 | 演示数据装载是工程需要，不是业务概念 |

## 全部 14 个

| 符号 | 归属文件 | 类别 | 用途 |
|---|---|---|---|
| `Quote` | `domain/pricing.py` | dataclass | 报价结果（值对象） |
| `Transition` | `domain/state_machine.py` | dataclass | 状态机边的描述 |
| `OccupancyPlan` | `domain/inventory.py` | dataclass | 占用计划（逐日新占用量） |
| `SeedOutcome` | `infrastructure/db/seed.py` | dataclass | 种子装载结果 |
| `Migration` | `infrastructure/db/migrate_runner.py` | dataclass | 一条迁移脚本的元数据 |
| `DomainError` | `domain/errors.py` | 异常基类 | 领域错误（带 `code`/`http_status`） |
| `ValidationError` | `domain/errors.py` | 异常 | 参数非法 → 422 |
| `IllegalTransitionError` | `domain/errors.py` | 异常 | 非法状态转换 → 409 |
| `PermissionDeniedError` | `domain/errors.py` | 异常 | 角色无权 → 403 |
| `NoAvailabilityError` | `domain/errors.py` | 异常 | 余量不足 → 409 |
| `DuplicateBookingError` | `domain/errors.py` | 异常 | 重复预订 → 409 |
| `InvalidStateError` | `domain/errors.py` | 异常 | 对象状态损坏 → 500 |
| `BookingEvent` | `domain/enums.py` | 枚举 | 8 个领域事件 |
| `ActorRole` | `domain/enums.py` | 枚举 | 4 类操作者 |

> `BookingStatus` 不在本表：它在类图里已登记（`<<enumeration>>`，第 84 行）。
