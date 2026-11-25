# 类图符号 → 代码落点白名单

本表是 `code/tools/check_uml_sync.py` 的唯一输入：**类图里有几个符号，代码里就必须有几个同名类**，
且每个符号都要写明落点文件与 `.puml` 行号（行号被脚本逐行比对，改类图不改本表会直接 FAIL）。

- 类图基线：`exp2/UML/UML类图.puml` v1.1（只读引用，不改动）
- 代码基线：`code/app`（`check_uml_sync.py --app code/app`）
- 19 个符号 = 13 核心类型（12 实体 + 1 枚举）+ 3 领域服务 + 3 仓储接口

| 符号 | 类别 | UML 位置 | 代码落点 | 说明 |
|---|---|---|---|---|
| UserAccount | 实体 | UML类图.puml:L18 | code/app/domain/models.py | 账号；口令校验依赖注入 |
| Hotel | 实体 | UML类图.puml:L28 | code/app/domain/models.py | 需平台审核通过才能售卖 |
| RoomType | 实体 | UML类图.puml:L39 | code/app/domain/models.py | 总房量是上限，非每日可售 |
| RoomInventory | 实体 | UML类图.puml:L48 | code/app/domain/models.py | 可售/占用落库，余量为派生 |
| RoomPrice | 实体 | UML类图.puml:L60 | code/app/domain/models.py | 逐日单价，整数分 |
| Booking | 实体 | UML类图.puml:L67 | code/app/domain/models.py | 唯一允许改状态的实体 |
| BookingStatus | 枚举 | UML类图.puml:L84 | code/app/domain/enums.py | 六状态；StrEnum |
| BookingNight | 实体 | UML类图.puml:L93 | code/app/domain/models.py | 逐晚价格快照 |
| IdempotencyKey | 实体 | UML类图.puml:L100 | code/app/domain/models.py | 幂等键独立表 + 弱引用 |
| StayRecord | 实体 | UML类图.puml:L107 | code/app/domain/models.py | 入住/退房/未入住流水 |
| AuditLog | 实体 | UML类图.puml:L115 | code/app/domain/models.py | 只追加，不建外键 |
| NotificationRecord | 实体 | UML类图.puml:L127 | code/app/domain/models.py | 取 UML∪数据设计并集（D-017） |
| HolidayCalendar | 实体 | UML类图.puml:L135 | code/app/domain/models.py | 平台级节假日字典 |
| BookingStateMachine | 领域服务 | UML类图.puml:L144 | code/app/domain/state_machine.py | 8 条允许边 + 5 条禁止边 |
| BookingService | 领域服务 | UML类图.puml:L151 | code/app/domain/services.py | 建单与状态流转编排 |
| InventoryService | 领域服务 | UML类图.puml:L158 | code/app/domain/services.py | 余量判定与占用计划 |
| BookingRepository | 仓储接口 | UML类图.puml:L168 | code/app/domain/repositories.py | 抽象类；实现留 S3 |
| InventoryRepository | 仓储接口 | UML类图.puml:L174 | code/app/domain/repositories.py | 抽象类；实现留 S3 |
| AuditLogRepository | 仓储接口 | UML类图.puml:L180 | code/app/domain/repositories.py | 抽象类；实现留 S3 |

## 口径说明

1. **类名逐字对齐**：Python 类名与 `.puml` 的 `as` 别名完全相同，不做 `SnakeCase` 化，
   这样脚本比对不需要任何映射表。
2. **仓储接口在领域层**：`repositories.py` 只写 `ABC` + `@abstractmethod`，SQLite 实现放
   `app/infrastructure/repositories/`（S3），依赖方向是"基础设施依赖领域"，反向箭头只有这一处。
3. **未登记的代码类**：脚本会打印 `extra_in_code`（如 `Migration`、`SeedOutcome` 等纯实现类），
   它们不来自类图，**不判失败**，但要能在评审时逐个说出"为什么类图不需要它"。
4. **行号会漂移**：一旦有人改 `exp2/UML/UML类图.puml`，本表必须同步更新行号，否则脚本 FAIL——
   这是刻意的：类图是只读基线，改动必须显式登记（见 `协作/变更/`）。
