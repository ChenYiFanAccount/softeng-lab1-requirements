# 大模型辅助记录（实验三）

> 用途：报告 R2/R3 的原始素材。每条记录一次真实交互，字段固定为
> `场景 / 输入 / 输出摘要 / 问题 / 人工处理 / 结论`。
> 说明：本项目使用两个模型角色——**执行者（代码生成与执行）** 与 **评审人（独立复核、跑命令、出判定）**，
> 评审人全程直读仓库，结论存 `协作/评审记录/`。下面的"人工处理"列指本人（陈一帆）的判断与改动。

| # | 场景 | 时间 |
|---|---|---|
| 1 | 方案生成与判据校验 | 2026-11-23 |
| 2 | 数据库与领域层代码生成 | 2026-11-25 |
| 3 | 状态机用例设计（13 条边） | 2026-11-25 |
| 4 | 并发与幂等的模拟用户测试 | 2026-11-25 |
| 5 | 代码风格检查与整改 | 2026-11-25 |
| 6 | 坏味道（disable）判定与压缩 | 2026-11-26 |
| 7 | 界面截图与布局缺陷定位 | 2026-11-26 |
| 8 | 报表口径缺陷（退房后营收归零） | 2026-11-26 |

## 记录 1：方案生成与判据校验

- **输入**：`exp3/实验三：软件实现与构建.md` 全文、`exp1/requirements.md`、`exp2/设计基线/` 三份文档、`exp2/UML/UML类图.puml`。
- **输出摘要**：`实验三_执行方案.md`（318 行）——三任务拆解、S0–S9 阶段表（每步含"做什么/怎么做/完成判据"）、代码量预算 2600–3400 行、风险表。
- **问题**：第一版把工期排成 7.2 天，而当时距截止只剩 6 天；且并发判据只写"用多线程测一下"，没有线程数与断言。
- **人工处理**：评审人第 1 轮指出后，本人删掉两个非必需阶段、把并发判据固定为 `--threads 200` 且断言 `success=1 fail=199`；并在方案里补"禁止重试取稳定结果"的红线。
- **结论**：方案可执行；工期压缩后按 S0–S9 逐阶段推进，每阶段交付一份交付说明。

## 记录 2：数据库与领域层代码生成

- **输入**：`exp2/设计基线/03_数据设计.md`（12 表字段与约束）、类图 19 个符号清单。
- **输出摘要**：`code/app/infrastructure/db/migrations/0001_init.sql`（12 表、部分唯一索引 `ux_booking_active_period`）、`connection.py`（`isolation_level=None` + `BEGIN IMMEDIATE` + `busy_timeout`）、`domain/` 11 个文件（实体、状态机、计价、库存、仓储接口）。
- **问题**：①模型第一版在 `sqlite3` 默认 `isolation_level=''` 下直接 `BEGIN IMMEDIATE`，运行即抛 `cannot start a transaction within a transaction`；②`Quote` 字段名被写成 `total_price_cents`，与实体字段不一致。
- **人工处理**：①把连接工厂固定为 `isolation_level=None` 并封装 `immediate_transaction()`，嵌套调用直接抛 `RuntimeError`；②按实体字段统一为 `total_cents`，并把"金额一律整数分"写进领域层 docstring。
- **结论**：`init_db.py --seed` 一次跑通：`tables=12`、`foreign_keys=1`、`integrity_check=ok`、`journal_mode=wal`。

## 记录 3：状态机用例设计（13 条边）

- **输入**：`exp1/项目参数.md` 的六状态、7 条允许转换（按触发者拆 8 条）、5 条禁止转换。
- **输出摘要**：`state_machine.py` 表驱动实现（`TRANSITIONS` 8 条 + `FORBIDDEN_TRANSITIONS` 5 条，无任何 `if status ==` 分支）；`test_state_machine.py` 13 条边用例 + 6 条规则用例。
- **问题**：①模型把"唯一 `(source,event)` 数"写成 7，实测是 8（`CONFIRM` 与 `AUTO_CHECK_IN` 是不同事件、同一目标）；②禁止边的错误消息断言写成了"包含来源状态中文名"，实际消息是"非法转换：酒店状态下的确认操作被拒绝（F4）"。
- **人工处理**：①改为三条断言：8 条 `TRANSITIONS`、8 个唯一 `(source,event)`、**6 个唯一 `(source,target)`**（并在报告里解释这正是"7 条边按触发者拆 8 条"的落库形态）；②改为断言 `code`/`http_status`/`details["from_status"]`。
- **结论**：13 条边用例全绿；`grep 'if.*\.status\s*=='` 命中 0。

## 记录 4：并发与幂等的模拟用户测试

- **输入**：S3 判据（200 线程、禁止重试）、下单事务设计。
- **输出摘要**：`tools/concurrency_probe.py`（`threading.Barrier(200)` 同步起跑、每线程独立连接、只计数不重试）；`test_idempotency.py` 4 条。
- **问题**：①探针第一版在 autocommit 连接上又写了 `conn.execute("COMMIT")`，报 `cannot commit - no transaction is active`；②200 线程跑完输出里带 `elapsed_ms`，三次结果无法逐字节比对。
- **人工处理**：①删掉多余的 COMMIT；②加 `--timing` 开关，默认不打印用时，使三次输出 SHA256 一致（`7CF9AD02…61F905`）。
- **结论**：`success=1 fail=199 locked_errors=0 negative_stock=0 booking_rows=1 booking_night_rows=1`，未出现一次 `database is locked`。

## 记录 5：代码风格检查与整改

- **输入**：`pylint code/app code/tools code/tests` 首轮输出（9.10）。
- **输出摘要**：`code/.pylintrc`（`init-hook` 注入 `code/` 到 `sys.path`、行长 100、允许中文方法名、disable `C0413/C2401/R0801` 各带理由）。
- **问题**：模型一开始靠"整文件重写"改长行，改出过两处语法错误（`self.room_types = (` 括号未闭合）；另有文档字符串里写了字面 `if booking.status ==` 与 `float(`，把 grep 判据打成命中 1。
- **人工处理**：①改用 `edit` 工具按行修改，改完立刻 `compileall`；②把判据正则收敛到 `check_source_rules.py` 一处登记，避免"证据口径比判据窄"。
- **结论**：pylint 10.00/10、0 message；五条源码规则命中 0。

## 记录 6：坏味道（disable）判定与压缩

- **输入**：评审意见"`# pylint: disable` 20 条 > 5 条上限"。
- **输出摘要**：14 条分类明细（`too-many-instance-attributes` 8、`too-many-arguments(+positional)` 6、其余 0），每条带 `文件:行 + 理由`。
- **问题**：模型第一反应是"改 `pylintrc` 放宽阈值"或"拆实体"，前者被评审人明确禁止，后者会动摇已通过的仓储与事务边界。
- **人工处理**：选择真改进——给 19 个按钮回调补 docstring（消 2 条）、把 infrastructure 导入提到模块顶层（消 2 条）、给 `Clock` 补 `source()`、给 `AccountService` 补 `check_available()`（消 2 条，各带用例）。
- **结论**：20 → 14 条且分类达标、0 条 error 级；新增 5 条用例（147 → 152）。

## 记录 7：界面截图与布局缺陷定位

- **输入**：评审意见"截图只拍到窗口左边 2/3，右侧「合计/状态」被截掉"。
- **输出摘要**：`take_screenshots.py` 改 `PrintWindow(PW_RENDERFULLCONTENT)` 整窗出图 + 纯 ctypes 手写 PNG（不引 Pillow）；`ui_chain.py` 8 步真点按钮链路。
- **问题**：模型连续 5 轮误判，先怀疑列宽、再怀疑 `pack` 顺序，实际根因是"进程非 DPI 感知 + `CopyFromScreen` 按屏幕坐标取像"，乘出来只有窗口的一部分；期间还拍到过别的应用窗口。
- **人工处理**：改为进程启动即 `SetProcessDpiAwareness(2)`、按 `GetWindowRect` 取整窗、抓完自检"PNG 宽高 == 窗口宽高 且 末列右界在图中"，不满足即 `exit≠0`；截图先落 `tmp_shots/` 复验后再覆盖仓库。
- **结论**：10 张截图 `1662×1016`，六列齐全；`ui_chain` 8 步 `check=passed`。

## 记录 8：报表口径缺陷（退房后营收归零）

- **输入**：评审人实测"订单退房后，营收两行全消失、对账 `diff=4`"。
- **输出摘要**：根因定位——`report_repository.py` 的 `ACTIVE_VALUES` 被营收、入住率、对账右侧三处共用，而 `ACTIVE_STATUSES` 不含 `CHECKED_OUT`。
- **问题**：模型最初认为"已退房的订单不该算营收"，与"退房只改状态、不释放占用"的事实矛盾；对账告警还打印了裸 `bookings=-`，运维无法分辨是漏打印还是真没订单。
- **人工处理**：拆成两套集合 `REVENUE_STATUSES`（含 `CHECKED_OUT`）与 `OCCUPYING_VALUES`；无关联订单时写 `bookings=NONE(无有效订单，库存多占)`；补 3 条用例（退房营收、退房 `diff=0`、告警不写裸 `-`）。
- **结论**：`PENDING/CONFIRMED/CHECKED_IN/CHECKED_OUT` 四态营收一致、对账 `diff=0`；该缺陷成为报告中"不符合预期时怎么做"的代表案例。
