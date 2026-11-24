# 酒店预订系统 · 实验三实现（exp3）

按 `exp2/UML/UML类图.puml` v1.1 与 `exp2/设计基线/` 实现的可运行桌面应用。本目录同时承载实验三的代码、UML 回改、报告素材与执行/评审协作记录。

- 课设手册：[`实验三：软件实现与构建.md`](实验三：软件实现与构建.md)
- 执行方案：[`实验三_执行方案.md`](实验三_执行方案.md)
- 协作章程（执行者 E / 评审人 R）：[`协作/章程.md`](协作/章程.md)
- 当前进度：[`协作/状态板.md`](协作/状态板.md) ｜ 决策：[`协作/决策日志.md`](协作/决策日志.md)

## 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 语言 / 运行时 | Python 3.12.6 | 标准库即可运行，无第三方运行期依赖 |
| 界面 | Tkinter 8.6（ttk） | 桌面应用，符合手册"建议桌面应用" |
| 存储 | SQLite 3.45.3（单文件） | 事务 + 行锁语义覆盖并发下单 |
| 开发期工具 | pylint 4.1.4、coverage | 仅风格与覆盖率举证，锁定版本 |

## 目录

```
exp3/
├── code/                  # 交付源码根（打包进 zip 的 code/）
│   ├── app/               # 应用代码：domain / application / infrastructure / ui 四层
│   ├── tests/             # 单元与集成测试（行数与 app/ 分列统计）
│   ├── tools/             # 开发期脚本：建库、种子、LOC 统计、并发探针、UML 同步检查
│   ├── docs/              # 证据（evidence/）、报告素材（report_materials/）、uml_map.md
│   ├── config/            # settings.json 等配置
│   └── data/              # 运行期 SQLite 文件目录（*.db 不入库）
├── docs/screenshots/      # 界面截图与 INDEX.md
├── 协作/                  # 执行/评审协作：章程、状态板、决策日志、任务书、评审记录、交付说明
└── 实验三_执行方案.md      # 实施方案（不进 zip）
```

## 运行（占位）

> S0 仅立骨架，尚未产出业务代码。唯一启动入口规划为 `code/run.py`（S6 提供），届时本节替换为：
> `D:\NJU\softengineering\exp3\.venv\Scripts\python code\run.py`

## 重建开发环境

```powershell
# 1) 虚拟环境（Python 3.12.6）
D:\softeng-env\venv\Scripts\python.exe -m venv .venv

# 2) 抓取开发期依赖 wheel 到 .wheels/（首次需联网；之后完全离线可重建）
.\.venv\Scripts\python.exe code\tools\fetch_wheels.py -r code\requirements-dev.txt -o .wheels

# 3) 离线安装（.wheels/ 已含 pylint 4.1.4 / coverage 7.17.5 及其传递依赖）
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .wheels -r code\requirements-dev.txt

# 4) 风格检查（pylintrc 于 S7 提供，届时追加 --rcfile code\config\pylintrc）
.\.venv\Scripts\python.exe -m pylint app
```

> 为何自带抓取脚本：本机 `pip` 访问 PyPI 的 HTTP 栈会长时间无响应（实测 >2 分钟拿不到索引页），而标准库 `urllib` 正常（0.8 秒取回 JSON）。故由 `fetch_wheels.py` 解析依赖并直接下载 wheel，再让 pip 离线安装。此取舍记入报告"实现与设计差异"。

## 仓库

本目录与 `exp1/`、`exp2/` **共用父仓库** `softengineering`（远端 `git@github.com:ChenYiFanAccount/softeng-lab1-requirements.git`），不另建子仓库；因此 `exp3/` 内不存在 `.git`，历史随父仓库统一管理，评审记录与代码天然同源。
