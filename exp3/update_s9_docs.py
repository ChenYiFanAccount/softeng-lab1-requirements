"""更新 S9 阶段的状态板与决策日志（幂等：重复运行不会重复追加）。"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(r"D:\NJU\softengineering\exp3")
BOARD = ROOT / "协作" / "状态板.md"
LOG = ROOT / "协作" / "决策日志.md"

SNAPSHOT = (
    "| 11-26（15:10） | **5054** | **2504** | **152** | 10.00/10（0 message） | 0 | "
    "S9：`交付包/实验3_241220024_陈一帆.zip`（230 条目、2.66 MB），顶层三项齐全；"
    "报告 PDF 17 页、首页含学号姓名；包内禁用文件 0 命中；证据 `S9_01`~`S9_03`；"
    "`gate-S7` 已打在 `3e8e202`（8 个 gate 标签齐） |"
)

DECISION = """## D-030　S9 打包口径（2026-11-26）

1. **zip 顶层只放三项**：`实验报告.pdf`、`UML/`、`code/`。DOCX 源文件不进包，留在 `exp3/report_src/` 便于改稿重导出。
2. **`code/` 用白名单式复制**：`robocopy` 排除 `__pycache__`、`data`、`.venv`、`.wheels`，并排除 `*.db`、`*.pyc`；打包后用 `zipfile` 名表正则复查，`matched=0` 才算通过。
3. **截图与报告图分开**：10 张界面图与 `INDEX.md` 进包（`code/docs/screenshots/`），报告首页渲染图 `report_cover.png` 作为 S9-4 的目检证据一并入库。
4. **`report_materials/` 只放客观素材**（`uml_extra_symbols.md`、`requirement_update.md`、`README.md` 声明），章节正文只在 PDF 内，避免"正文混进素材目录"。
5. **工作区清理是打包前置条件**：`exp3` 下曾有 330+ 个测试临时目录（每个都带 `.db`），已全部删除并复查 `*.db` 只剩 `code/data/` 三个开发库（gitignore 内）。
6. **cslab-cms 提交由业主执行**，S9-7 的回执只能本人提供；本阶段只保证包与材料就绪、复跑命令可验证。
"""


def update_board() -> None:
    text = BOARD.read_text(encoding="utf-8")
    rows = {
        "| G5 | S7 + S8 + S9 | R1 已出 |": (
            "| G5 | S7 + S8 + S9 | R1 已出 | **S7 整改已交；S8 已闭合（8/8 gate 标签）；S9 已交，待终验** | "
            "S7-7 由 20 → **14 条**（8/6/0，0 条 error 级）；`gate-S7` 已打在 `3e8e202`，8 个 gate 标签齐；"
            "S8 交付说明 S8-1 已改「8/8 通过」；交付包 `230` 条目、顶层三项、禁用文件 0 | "
            "`评审记录/S7_第1轮.md` · `交付/S8/交付说明.md` · `交付/S9/交付说明.md` | 11-26 15:10 |"
        ),
        "| S8 | Git 与远程 |": (
            "| S8 | Git 与远程 | **已闭合**（`gate-S7` 打在 `3e8e202`，S8-1 8/8；业主确认无需再等评审） | "
            "S8-1~S8-5（推送目标 = 父仓库）；`git log origin/main --oneline -1 -- exp3` 命中 `[S<n>]` 提交（S0-R1-02） | "
            "`交付/S8/交付说明.md` · `code/docs/evidence/S8_0*.txt` |"
        ),
        "| S9 | 报告与打包 |": (
            "| S9 | 报告与打包 | **已交，待终验**（11-26 15:10；包 230 条目 2.66 MB） | "
            "S9-1~S9-7（S9-6 按 CR-02 / D-014 替换；S9-7 待业主提交回执） | "
            "`交付/S9/交付说明.md` · `code/docs/evidence/S9_0*.txt` |"
        ),
    }
    lines = text.splitlines()
    for index, line in enumerate(lines):
        for prefix, replacement in rows.items():
            if line.startswith(prefix):
                lines[index] = replacement
                break
    text = "\n".join(lines)
    text = text.replace("> 章程：`协作/章程.md`　最近更新：2026-11-26 03:50",
                        "> 章程：`协作/章程.md`　最近更新：2026-11-26 15:10")
    if "11-26（15:10）" not in text:
        text = text.rstrip("\n") + "\n" + SNAPSHOT + "\n"
    BOARD.write_text(text, encoding="utf-8")


def update_log() -> None:
    text = LOG.read_text(encoding="utf-8")
    if "## D-030" not in text:
        text = text.rstrip("\n") + "\n\n" + DECISION
    LOG.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    update_board()
    update_log()
    print("board and log updated")
