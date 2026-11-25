"""应用包根。

分层（对应 `exp2/设计基线/02_模块划分与交互.md` 的 4 层 + M1–M10 纵切）：

- `domain/`：实体、值对象、状态机、领域服务与仓储**接口**，不依赖 sqlite3；
- `application/`：用例编排（下单、改期、取消、审批、对账）；
- `infrastructure/`：仓储实现、SQLite 连接与迁移、种子数据；
- `ui/`：Tkinter 界面，只调用 application 层。

S1 只落地 `infrastructure/` 的数据底座，其余分层自 S2 起逐个补齐。
"""
