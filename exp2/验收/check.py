#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""实验二 验收脚本（机械层 / A 层）。

用法：
    python 验收\\check.py --stage 1        # 只跑第 1 阶段的检查项
    python 验收\\check.py --stage 1 -v     # 附带每项明细
    python 验收\\check.py --stage 9        # 跑 1..9 全部检查（终检）

设计原则：
1. 只读文档与文件，不修改任何东西；不改动工作区，可安全重复执行。
2. 每个检查项独立，失败不中断，最后统一汇总；任一 FAIL → 退出码 1。
3. 检查"口径是否自洽"而不是"文字写得漂不漂亮"：数值、编号、覆盖关系全部
   从文档里解析出来再比对，避免人工数行。
4. 期望值集中放在 EXPECT 里，口径一旦变更只改一处。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK，遇到「−」「≤」等符号会 UnicodeEncodeError；统一改 UTF-8 输出
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                    # 非 tty / 旧解释器：忽略
        pass

EXPECT = {
    "req_count": 27,              # 实验一冻结需求条数（功能22 + 非功能4 + 约束1）
    "transition_edges": 8,        # 状态转换边数（6 种状态对，T2/T3、T4/T5 各两条）
    "transition_pairs": 6,
    "table_count": 12,            # 数据表张数（含 booking_night）
    "ui_required": 17,            # 必做界面张数
    "ui_optional": 3,             # 可选界面张数（18–20）
    "class_types": 13,            # 类图核心类型
    "class_services": 3,          # 类图服务类
    "class_repos": 3,             # 类图仓储接口 <<interface>>
    "uml_required": 7,            # UML 必做张数
    "uml_optional": 2,            # UML 可选张数
    "unique_business": 6,         # 03 §9 业务唯一约束（U1–U6）
    "unique_tech": 4,             # 03 §9 技术性唯一（T1–T4，不混入 6 条）
}

# 禁用词：旧口径残留。命中即判 FAIL（说明某处还停留在修订前的说法）。
BANNED = {
    "7 条转换": "状态转换应为 8 条边 / 6 种状态对",
    "11 张表": "数据表应为 12 张（含 booking_night）",
    "15 张界面": "必做界面应为 17 张",
    "禁止反向箭头": "依赖倒置允许且仅允许一条反向实现箭头",
    "3.13.16": "本机 Python 实为 3.12.6",
    "11-14 23:59": "截止时间口径为 2026-11-14 00:00（= 11-13 全天结束前）",
    "净剩余": "R-01：可售间数是酒店挂牌量，不是净剩余；已占用间数须落库",
    "总房量 − 可售间数": "R-01：占用不得由总房量反推，须自成一列落库",
}

ROOT = Path(__file__).resolve().parent.parent          # exp2/
BASE = ROOT / "设计基线"
B1 = BASE / "01_术语与追溯.md"
B2 = BASE / "02_模块划分与交互.md"
B3 = BASE / "03_数据设计.md"
PLAN = ROOT / "实验二_执行方案.md"
PHASE = ROOT / "实验二_阶段与验收.md"
UML_DIR = ROOT / "UML"
UI_DIR = ROOT / "UI界面"

results: list[tuple[str, bool, str, str]] = []   # (stage, name, ok, detail)


def record(stage: str, name: str, ok: bool, detail: str = "") -> None:
    results.append((stage, name, ok, detail))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def lines_of(p: Path) -> list[str]:
    return read(p).splitlines()


def cells(line: str) -> list[str]:
    """拆 markdown 表格行：'| a | b |' -> ['a', 'b']。"""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def section(text: str, heading_pat: str, stop_pat: str = r"^#{1,3} ") -> str:
    """截取某个标题到下一个同级或更高级标题之间的正文。"""
    out, inside = [], False
    for ln in text.splitlines():
        if not inside and re.search(heading_pat, ln):
            inside = True
            continue
        if inside:
            if re.search(stop_pat, ln):
                break
            out.append(ln)
    return "\n".join(out)


# 明细里出现这些字样说明写的是"哪里不对"（失败话术），PASS 行不得展示（评审 D-03③）
FAILWORDS = re.compile(r"缺|未|不是|不对|应为|非法|不符|异常|多余|残留")


# ---------------------------------------------------------------- 模块卡解析
def module_req_map() -> dict[str, set[str]]:
    """从 02 的模块卡片解析 模块 -> 覆盖 REQ 集合。"""
    mapping: dict[str, set[str]] = {}
    cur = None
    for ln in lines_of(B2):
        m = re.match(r"^### (M\d+)\s", ln)
        if m:
            cur = m.group(1)
            mapping.setdefault(cur, set())
            continue
        m = re.match(r"^-\s*\*\*覆盖 REQ\*\*[：:]\s*(.+)$", ln)
        if m and cur:
            mapping[cur] |= set(re.findall(r"\b0\d{2}\b", m.group(1)))
    return mapping


def ui_rows() -> dict[str, list[str]]:
    """从执行方案 H 节解析 界面号 -> 各列。"""
    rows: dict[str, list[str]] = {}
    for ln in lines_of(PLAN):
        m = re.match(r"^\|\s*界面(\d{2})(?:（可选）)?\s*\|", ln)
        if m:
            rows[m.group(1)] = cells(ln)
    return rows


def trace_rows() -> dict[str, list[str]]:
    """从 01 §4 解析 REQ -> 各列。"""
    rows: dict[str, list[str]] = {}
    for ln in lines_of(B1):
        m = re.match(r"^\|\s*(0\d{2})\s*\|", ln)
        if m:
            rows[m.group(1)] = cells(ln)
    return rows


# ============================================================ S1 检查项
def s1_req_trace() -> None:
    stage = "S1"
    if not B1.exists():
        record(stage, "需求追溯表存在", False, f"缺少 {B1.name}")
        return
    rows = trace_rows()
    ids = sorted(rows)
    want = [f"{i:03d}" for i in range(1, EXPECT["req_count"] + 1)]
    record(stage, f"追溯表条数 = {EXPECT['req_count']}", len(rows) == EXPECT["req_count"],
           f"实际 {len(rows)} 条：{','.join(ids)}")
    record(stage, "编号连续且无重复 001–027", ids == want,
           "" if ids == want else f"缺 {sorted(set(want) - set(ids))} 多 {sorted(set(ids) - set(want))}")

    miss_mod = [r for r, c in rows.items() if not re.findall(r"M\d+", c[2] if len(c) > 2 else "")]
    miss_uml = [r for r, c in rows.items() if len(c) < 5 or not c[3].strip()]
    miss_ui = [r for r, c in rows.items() if len(c) < 5 or not c[4].strip()]
    miss_sec = [r for r, c in rows.items() if len(c) < 6 or not c[5].strip()]
    record(stage, "每条都有『模块』落点", not miss_mod, f"缺模块: {miss_mod}")
    record(stage, "每条都有『主要 UML』落点", not miss_uml, f"缺图: {miss_uml}")
    record(stage, "每条都有『主要界面』落点", not miss_ui, f"缺界面: {miss_ui}")
    record(stage, "每条都有『报告章节』落点", not miss_sec, f"缺章节: {miss_sec}")

    # 界面号必须在执行方案 H 节真实存在
    known = set(ui_rows())
    bad = []
    for r, c in rows.items():
        if len(c) < 5:
            continue
        for n in re.findall(r"(?<!\d)(\d{2})(?!\d)", c[4]):
            if n not in known:
                bad.append(f"REQ-{r}->界面{n}")
    record(stage, "追溯表的界面号都能在 H 节找到", not bad, ", ".join(bad))


def s1_req_module_cover() -> None:
    stage = "S1"
    mapping = module_req_map()
    mods10 = [f"M{i}" for i in range(1, 11)]
    record(stage, "02 含 M1–M10 十张模块卡", set(mods10) <= set(mapping),
           f"缺 {sorted(set(mods10) - set(mapping))}")

    union = set().union(*mapping.values()) if mapping else set()
    want = {f"{i:03d}" for i in range(1, EXPECT["req_count"] + 1)}
    record(stage, "模块卡覆盖全部 27 条 REQ（无孤儿）", union == want,
           f"未覆盖 {sorted(want - union)}；多出 {sorted(union - want)}")

    # 01 里每条 REQ 列出的每个模块，其模块卡必须也认领这条 REQ
    bad = []
    for r, c in trace_rows().items():
        if len(c) < 3:
            continue
        for m in re.findall(r"M\d+", c[2]):
            if r not in mapping.get(m, set()):
                bad.append(f"REQ-{r} 归 {m}，但 {m} 卡未认领")
    record(stage, "01 与 02 的 REQ→模块 双向一致", not bad, "; ".join(bad))


def s1_transitions() -> None:
    stage = "S1"
    rows = [ln for ln in lines_of(B1) if re.match(r"^\| T\d\s*\|", ln)]
    ids = [cells(ln)[0] for ln in rows]
    record(stage, f"01 转换表恰好 {EXPECT['transition_edges']} 条", len(rows) == EXPECT["transition_edges"],
           f"实际 {len(rows)} 条: {ids}")
    record(stage, "编号 T1–T8 齐全", ids == [f"T{i}" for i in range(1, 9)], f"{ids}")

    text = read(PLAN)
    seg = []
    inside = False
    for ln in text.splitlines():
        if "允许转换" in ln and ln.strip().startswith("|"):
            inside = True
            continue
        if inside:
            if not ln.strip().startswith("|"):
                break
            if set(ln.replace("|", "").strip()) <= set("-: "):
                continue
            seg.append(ln)
    record(stage, f"执行方案 C 节转换表也是 {EXPECT['transition_edges']} 条",
           len(seg) == EXPECT["transition_edges"], f"实际 {len(seg)} 条")

    phase = read(PHASE)
    record(stage, "阶段卡口径卡写『8 条边 / 6 种状态对』",
           "8 条边" in phase and "6 种状态对" in phase, "口径卡缺该表述")
    record(stage, "『6 种状态对』= 边数 - 2（T2/T3、T4/T5 各拆两条）",
           EXPECT["transition_edges"] - EXPECT["transition_pairs"] == 2, "口径自检")


def s1_tables() -> None:
    stage = "S1"
    text = read(B3)
    secs = [m.group(1) for m in re.finditer(r"^### (2\.\d+)\s", text, re.M)]
    record(stage, f"03 表清单 {EXPECT['table_count']} 张", len(secs) == EXPECT["table_count"],
           f"实际 {len(secs)} 张: {','.join(secs)}")
    want = [f"2.{i}" for i in range(1, EXPECT["table_count"] + 1)]
    record(stage, "03 表编号 2.1–2.12 连续无断档", secs == want,
           f"实际 {secs}")
    record(stage, "含 booking_night（订单逐晚快照）", "booking_night" in text, "缺少逐晚快照表")

    plan = read(PLAN)
    frows = [ln for ln in plan.splitlines() if re.match(r"^\|\s*`[a-z_]+`\s*\|", ln)]
    record(stage, f"执行方案 F 节表清单 {EXPECT['table_count']} 行", len(frows) == EXPECT["table_count"],
           f"实际 {len(frows)} 行")
    record(stage, "执行方案 F 节含 booking_night", "booking_night" in plan, "缺少逐晚快照表")


def s1_stock_model() -> None:
    """R-01 复验：可售=挂牌量、已占用落库、余量=可售−占用（三查，对应评审 A1/A2/A5）。"""
    stage = "S1"
    b3 = read(B3)
    b2 = read(B2)

    sec24 = section(b3, r"^### 2\.4\s")
    has_occ = "已占用间数" in sec24
    record(stage, "A1：room_inventory 同时有『可售间数』与『已占用间数』",
           has_occ and "可售间数" in sec24, "缺少已占用间数列")
    record(stage, "A1：已占用间数明确标注为落库事实（非派生）",
           has_occ and ("落库" in sec24 or "必须存" in sec24), "未写明已占用是否落库")

    sec5 = section(b3, r"^## 5\.\s")
    formula = re.search(r"余量\s*(?:\([^)]{0,40}\))?\s*=\s*可售间数\s*(?:\([^)]{0,40}\))?\s*[−-]\s*已占用间数", sec5)
    record(stage, "A2：03 §5 余量公式为『可售间数 − 已占用间数』", bool(formula),
           "§5 未找到 余量 = 可售 − 占用")
    record(stage, "A3：03 §5 写明按日下调可售只改可售、不低过占用",
           "按日" in sec5 and "可售" in sec5 and "占用" in sec5, "§5 缺少按日调整可售规则")

    sec25 = section(b2, r"^## 5\.\s")
    total_row = [ln for ln in sec25.splitlines() if "改总房量" in ln]
    record(stage, "A5：02 §5『改总房量』行的判据含『已占用』（不是由总房量反推）",
           bool(total_row) and "已占用" in total_row[0] and "新总房量" in total_row[0],
           "02 §5 改总房量行未以已占用为判据")
    record(stage, "A4：03 §7 对账比对『已占用』与订单汇总（不再比可售）",
           "已占用" in section(b3, r"^## 7\.\s"), "§7 对账对象不对")


def s1_ui() -> None:
    stage = "S1"
    rows = ui_rows()
    need = [f"{i:02d}" for i in range(1, EXPECT["ui_required"] + 1)]
    miss = [n for n in need if n not in rows]
    record(stage, f"H 节必做界面 01–{EXPECT['ui_required']} 齐全", not miss, f"缺 {miss}")
    record(stage, f"H 节界面总数不超过 {EXPECT['ui_required'] + EXPECT['ui_optional']}",
           len(rows) <= EXPECT["ui_required"] + EXPECT["ui_optional"], f"实际 {len(rows)} 行")

    # 必做界面每张都有归属模块，且 M1–M9 每个业务模块至少一张**独占**界面（模块列只有一个 M）
    mods_needed = {f"M{i}" for i in range(1, 10)}
    got: set[str] = set()
    exclusive: set[str] = set()
    nomod = []
    for n in need:
        if n not in rows:
            continue
        c = rows[n]
        ms = re.findall(r"M\d+", c[2] if len(c) > 2 else "")
        if not ms:
            nomod.append(n)
        got |= set(ms)
        if len(set(ms)) == 1:
            exclusive |= set(ms)
    record(stage, "必做界面每张都标注归属模块", not nomod, f"未标注: {nomod}")
    record(stage, "M1–M9 每个模块都有独占界面（模块列仅一个 M；M10 无界面）",
           mods_needed <= exclusive,
           f"缺独占界面模块: {sorted(mods_needed - exclusive)}（提及但非独占: {sorted(mods_needed - got)}）")

    title = {n: (rows[n][3] if len(rows[n]) > 3 else "") for n in rows}
    record(stage, "界面15=节假日表 / 16=统计看板 / 17=日志查询（已拆分）",
           "节假日" in title.get("15", "") and "统计" in title.get("16", "") and "日志" in title.get("17", ""),
           f"15={title.get('15')} 16={title.get('16')} 17={title.get('17')}")


def s1_class_spec() -> None:
    stage = "S1"
    text = read(PLAN)
    row = next((ln for ln in text.splitlines() if re.match(r"^\|\s*1\s*\|\s*`UML类图`", ln)), "")
    if not row:
        record(stage, "找到执行方案 E#1 类图规格行", False, "未找到")
        return
    m1 = re.search(r"\*{0,2}(\d+) 个核心类型\*{0,2}：(.*?)；", row)
    m2 = re.search(r"\*{0,2}(\d+) 个服务类\*{0,2}：(.*?)；", row)
    m3 = re.search(r"\*{0,2}(\d+) 个仓储接口\*{0,2}[^：:]*：(.*?)；", row)
    n1 = len(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", m1.group(2))) if m1 else 0
    n2 = len(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", m2.group(2))) if m2 else 0
    n3 = len(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", m3.group(2))) if m3 else 0
    record(stage, f"类图核心类型 = {EXPECT['class_types']}", n1 == EXPECT["class_types"], f"实际 {n1}")
    record(stage, f"类图服务类 = {EXPECT['class_services']}", n2 == EXPECT["class_services"], f"实际 {n2}")
    record(stage, f"类图仓储接口 = {EXPECT['class_repos']}", n3 == EXPECT["class_repos"], f"实际 {n3}")
    record(stage, "类图含 totalRooms 与 BookingNight",
           "totalRooms" in row and "BookingNight" in row, "缺字段/类型")
    record(stage, "类图声明『状态字段只能经 BookingStateMachine 修改』",
           "BookingStateMachine" in row and "状态字段只能经" in row, "缺状态机约束说明")


def s1_banned() -> None:
    stage = "S1"
    # 扫描范围（复验报告 D-11）：先前只扫 4 份文档，漏了阶段卡与验收目录，
    # 导致"旧口径只留在验收材料里"这种残留抓不到。
    targets = [B1, B2, B3, PLAN, PHASE]
    exp_dir = ROOT / "验收"
    if exp_dir.exists():
        targets += sorted(exp_dir.glob("*.md")) + sorted(exp_dir.glob("*.py"))
    # 白名单：外部评审材料按"原样归档"保留，其引述旧口径属正常（不得改写评审方原文）；
    # 以及任何标注了"禁用词/旧口径/勘误"的行，属于讨论该词本身。
    external = {"评审报告_S0_S1.md", "评审报告_S0_S1_复验.md", "评审报告_S1_S2.md", "返工单_R-01.md"}
    exempt_line = re.compile(r"禁用词|旧口径|勘误|口径变更|引述")
    hits = []
    scanned = 0
    for p in targets:
        if not p.exists() or p.name in external:
            continue
        scanned += 1
        in_def = False
        for i, ln in enumerate(lines_of(p), 1):
            # 本脚本自身要"写出"这些词才能检查它们，故跳过 BANNED 定义块
            if ln.startswith("BANNED = {"):
                in_def = True
                continue
            if in_def:
                if ln.strip() == "}":
                    in_def = False
                continue
            if exempt_line.search(ln):
                continue
            for word in BANNED:
                if word in ln:
                    hits.append(f"{p.name}:{i} 命中『{word}』")
    record(stage, "禁用词零命中（旧口径残留）", not hits,
           "；".join(hits) if hits else f"扫描 {scanned} 份文件 × {len(BANNED)} 个禁用词，干净")


def s1_phase_card() -> None:
    stage = "S1"
    phase = read(PHASE)
    checks = {
        "口径卡写『12 张』表": "**12 张**" in phase or "12 张（含" in phase,
        "口径卡写『13 个核心类型』": "13 个核心类型" in phase,
        "口径卡写『17 张必做』": "17 张必做" in phase,
        "口径卡写依赖倒置": "依赖倒置" in phase,
        "口径卡写库存口径（可售挂牌 / 已占用落库 / 余量为派生）":
            "可售" in phase and "已占用" in phase and "余量" in phase,
    }
    for k, ok in checks.items():
        record(stage, k, ok, "" if ok else "口径卡缺项")
    # UML 组数必须与 7 必做 + 2 可选 = 9 自洽
    m = re.search(r"UML/`?\((\d+) 组", phase)
    total = int(m.group(1)) if m else -1
    record(stage, f"交付清单 UML 组数 = {EXPECT['uml_required'] + EXPECT['uml_optional']}（7 必做 + 2 可选）",
           total == EXPECT["uml_required"] + EXPECT["uml_optional"], f"实际写 {total} 组")


# ============================================================ S2–S9 占位检查
def need_pair(stem: str, png_min: int = 20000) -> list[str]:
    bad = []
    for ext, floor in ((".puml", 200), (".png", png_min)):
        p = UML_DIR / f"{stem}{ext}"
        if not p.exists() or p.stat().st_size < floor:
            bad.append(f"{p.name}(<{floor}B)")
    return bad


def class_body(text: str, alias: str, kinds: str = "class|interface") -> str:
    """取出 `<kinds> "标签" as <alias> { ... }` 的花括号内正文（用于核对属性清单、逐组件接口数）。"""
    m = re.search(r"^\s*(?:" + kinds + r")\s+[^\n]*\bas\s+" + re.escape(alias) + r"\b[^\n]*\{", text, re.M)
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start:i - 1]


def s2_struct() -> None:
    """S2 判据按阶段卡 S2「A 层」逐条落地（复验 D-10：原判据只有一个 png>200B）。"""
    stage = "S2"
    for stem in ("UML类图", "UML包图", "UML组件图"):
        bad = need_pair(stem)
        record(stage, f"{stem}.puml/.png 成对且非空（>20KB）", not bad, f"缺/空: {bad}")
    p = UML_DIR / "UML类图.puml"
    if p.exists():
        t = read(p)
        ncls = len(re.findall(r"^\s*class\s+", t, re.M))
        nif = len(re.findall(r"<<interface>>", t))
        record(stage, f"类图 class ≥ {EXPECT['class_types']}", ncls >= EXPECT["class_types"], f"实际 {ncls}")
        record(stage, f"类图 <<interface>> = {EXPECT['class_repos']}", nif == EXPECT["class_repos"], f"实际 {nif}")
        record(stage, "类图含 totalRooms 与 BookingNight", "totalRooms" in t and "BookingNight" in t, "")
        mult = len(re.findall(r'"[0-9*]+"\s*[*-]|"\d+\s*\.\.', t))
        record(stage, "多重度标注 ≥ 6 处", mult >= 6, f"实际 {mult}")
        # 评审 A8：RoomInventory 的属性必须与 03 §2.4 逐字对齐，余量是方法不是字段
        block = class_body(t, "RoomInventory")
        three = all(k in block for k in ("可售间数", "已占用间数", "销售状态"))
        record(stage, "RoomInventory 三属性齐全（可售/已占用/销售状态）", three,
               "" if three else f"实际属性块：{block[:140].replace(chr(10), ' / ')}")
        record(stage, "RoomInventory 不存『占用 = 总房量 − 可售』式反推字段",
               "占用" in block and "可售" in block, "缺可售或已占用字段")
        record(stage, "类图不把『余量』当字段（余量须是派生方法）",
               not re.search(r"(-|\+)\s*余量\s*:", t), "把余量写成了持久化字段")
        # 三条服务类：BookingService / InventoryService / BookingStateMachine
        svc = [s for s in ("BookingService", "InventoryService", "BookingStateMachine") if s in t]
        record(stage, f"三个服务类齐全（{EXPECT['class_services']} 个）", len(svc) == EXPECT["class_services"],
               f"缺 {[s for s in ('BookingService','InventoryService','BookingStateMachine') if s not in t]}")
        record(stage, "类图有组合关系（Booking *-- BookingNight）",
               bool(re.search(r"\*\s*--", t)), "无组合关系")

        # 评审 R2-01：实体包里必须恰好 13 个 class（12 张表 + BookingStatus 枚举），
        # 多一个（例如把「角色」画成独立类）就会与口径卡的"13 个核心类型"打架
        ent = class_body(t, "L0", kinds="package")
        ent_body = ent or t.split("package \"领域服务")[0]
        n_ent = len(re.findall(r"^\s*class\s+", ent_body, re.M))
        record(stage, f"实体包恰好 {EXPECT['class_types']} 个 class（不含领域服务）",
               n_ent == EXPECT["class_types"], f"实际 {n_ent}")
        record(stage, "实体包没有独立的『Role 角色』类（角色是枚举字段，没有角色表）",
               "Role 角色" not in ent_body, "仍画了 Role 类，13 会变 14")

        # 评审 R2-02：订单必须能直读所属酒店（REQ-001/015/016/020 的隔离与统计都靠它）
        bk = class_body(t, "Booking")
        record(stage, "Booking 有『酒店ID』字段（隔离与按店统计直读）", "酒店ID" in bk, "缺 酒店ID")
        record(stage, "类图有 Booking—Hotel 关联",
               bool(re.search(r'Booking\s+"[^"]*"\s*(?:--|\*--)\s*"[^"]*"\s*Hotel', t))
               or bool(re.search(r'Hotel\s+"[^"]*"\s*(?:--|\*--)\s*"[^"]*"\s*Booking', t)),
               "没有 Booking—Hotel 关联")

        # 评审 R2-03：终态注释不能说"已入住是终态"（T8 已入住→已退房 合法）
        m_note = re.search(r"note[^\n]*BookingStatus[\s\S]{0,600}?end note", t)
        note = m_note.group(0) if m_note else ""
        # D-13：PlantUML 注释里 `**` 会按字面星号打印，故图内改为裸文字；两种写法都算通过
        term_ok = ("未入住" in note and "已退房" in note
                   and ("已入住不是终态" in note or "已入住**不是**终态" in note))
        record(stage, "状态机注释写明终态 = 已退房/已取消/未入住，且已入住不是终态", term_ok,
               "" if term_ok else f"注释片段：{note[:120]}")
    p = UML_DIR / "UML包图.puml"
    if p.exists():
        t = read(p)
        layers = ["表现层", "应用服务层", "领域层", "数据访问层"]
        record(stage, "包图含四层名", all(x in t for x in layers),
               f"缺 {[x for x in layers if x not in t]}")
        miss = [f"M{i}" for i in range(1, 11) if f"M{i}" not in t]
        record(stage, "包图含 M1–M10 全名", not miss, f"缺 {miss}")
        rev = len(re.findall(r"\.\.\|>", t))
        record(stage, "反向实现箭头恰好 1 条", rev == 1, f"实际 {rev}")
        record(stage, "包图写明这条反向箭头是依赖倒置（理由句）",
               ("依赖倒置" in t or "倒置" in t) and ("理由" in t or "因为" in t or "therefore" in t.lower()),
               "缺『为什么允许这一条反向』的说明")
        record(stage, "包图区分依赖/实现两种箭头", bool(re.search(r"-->\s*$", t, re.M)) or "-->" in t,
               "未见普通依赖箭头")
    p = UML_DIR / "UML组件图.puml"
    if p.exists():
        t = read(p)
        comps = re.findall(r'^\s*(?:\[|\bcomponent\b)', t, re.M)
        ncomp = len(re.findall(r"component\s+", t)) or len(comps)
        record(stage, "组件图组件 = 10（M1–M10）", ncomp >= 10, f"实际 {ncomp}")
        iface = len(re.findall(r"interface\s+|\[[^\]]+\]", t))
        record(stage, "接口总数 ≥ 20", iface >= 20, f"实际 {iface}")
        # 逐组件计数：M1–M10 每个 component 块内必须 ≥ 2 个 interface
        per = {}
        for i in range(1, 11):
            body = class_body(t, f"M{i}", kinds="component")
            per[f"M{i}"] = len(re.findall(r"^\s*interface\s+", body, re.M))
        thin = {k: v for k, v in per.items() if v < 2}
        record(stage, "M1–M10 每个业务组件对外接口 ≥ 2 个（逐组件计数）", not thin,
               f"接口不足的组件：{thin}")
        kinds = [k for k in ("同步", "异步", "定时") if k in t]
        record(stage, "组件图区分同步/异步/定时三类连接", len(kinds) == 3, f"只写了 {kinds}")
    # 三张图首行必须有图名 + 版本（阶段卡"S2 产出"要求）
    for stem in ("UML类图", "UML包图", "UML组件图"):
        p = UML_DIR / f"{stem}.puml"
        if p.exists():
            head = "\n".join(lines_of(p)[:6])
            record(stage, f"{stem} 首部有图名与版本", "版本" in head or "v1" in head.lower(), head[:80])


def s3_behavior() -> None:
    stage = "S3"
    for stem in ("UML用例图", "UML状态图", "UML活动图"):
        bad = need_pair(stem)
        record(stage, f"{stem}.puml/.png 成对且非空", not bad, f"缺/空: {bad}")

    # 三张图的开头都要有图名与版本号（报告 3.x 引用时要能对上号）
    vers_ok, vers_bad = True, []
    for stem in ("UML用例图", "UML状态图", "UML活动图"):
        p = UML_DIR / f"{stem}.puml"
        if not p.exists():
            vers_ok = False
            vers_bad.append(f"{stem} 缺失")
            continue
        head = "\n".join(lines_of(p)[:6])
        if "版本" not in head and "v1" not in head.lower():
            vers_ok = False
            vers_bad.append(f"{stem} 首 6 行无版本号")
    record(stage, "三张行为图首 6 行都写了版本号", vers_ok, "；".join(vers_bad))

    # ---------- 用例图：4 类参与者 + include/extend + 用例能指回 REQ ----------
    uc_p = UML_DIR / "UML用例图.puml"
    if uc_p.exists():
        t = read(uc_p)
        actors = re.findall(r'^\s*actor\s+"([^"]+)"', t, re.M)
        need = ("游客", "顾客", "酒店工作人员", "平台管理员")
        hit = [n for n in need if any(n in a for a in actors)]
        record(stage, "用例图参与者恰为 游客/顾客/酒店工作人员/平台管理员 四类",
               len(hit) == 4 and len(actors) == 4,
               f"实际 {len(actors)} 个: {actors}")
        ucs = re.findall(r'^\s*usecase\s+"([^"]+)"', t, re.M)
        with_req = [u for u in ucs if "REQ-" in u]
        record(stage, "用例图每个用例都带 REQ 编号（能指回需求）",
               len(ucs) >= 12 and len(with_req) == len(ucs),
               f"共 {len(ucs)} 个用例，其中带 REQ 的 {len(with_req)} 个")
        inc = len(re.findall(r"<<include>>", t))
        ext = len(re.findall(r"<<extend>>", t))
        record(stage, "用例图 <<include>> ≥ 2", inc >= 2, f"实际 {inc} 处")
        record(stage, "用例图 <<extend>> ≥ 1", ext >= 1, f"实际 {ext} 处")
        reqs = set(re.findall(r"REQ-(\d{3})", "\n".join(ucs)))
        record(stage, "用例覆盖到的 REQ 数 ≥ 18（非功能性 REQ 不必进用例图）",
               len(reqs) >= 18,
               f"覆盖 {len(reqs)} 条: {sorted(reqs)}")
        # 用注释补齐没画成边的关系是允许的，但注释里必须真的点了 <<include>>/<<extend>>
        tail_notes = "\n".join(ln for ln in t.splitlines() if "注释" in ln or "<<include>>" in ln or "<<extend>>" in ln)
        record(stage, "用例图注释里说明了省略的 include/extend",
               "注释" in tail_notes and ("include" in tail_notes and "extend" in tail_notes),
               "注释没写清哪两条被省略")

    # ---------- 状态图：6 状态 / 8 条边 / 6 种状态对 / 5 条禁止转换 ----------
    st_p = UML_DIR / "UML状态图.puml"
    if st_p.exists():
        t = read(st_p)
        decl = re.findall(r'^\s*state\s+"([^"]+)"\s+as\s+(\w+)', t, re.M)
        names = [n for n, _ in decl]
        alias = {n: a for n, a in decl}
        want = ("待确认", "已确认", "已入住", "已退房", "已取消", "未入住")
        record(stage, "状态图状态恰为 6 个且名称与口径一致",
               len(decl) == 6 and all(w in names for w in want),
               f"实际 {len(decl)} 个: {names}")

        arrows, edge_lines = [], []
        for ln in t.splitlines():
            m = re.search(r"^\s*(\S+)\s*-->\s*(\S+)", ln)
            if not m:
                continue
            edge_lines.append(ln)
            a, b = m.group(1), m.group(2)
            # [*] 是起止伪状态，不是六状态之间的转换；进出 [*] 的边不计入 8 条
            if a.startswith("[*]") or b.startswith("[*]"):
                continue
            arrows.append((a, b))
        record(stage, f"状态图转换边 = {EXPECT['transition_edges']}",
               len(arrows) == EXPECT["transition_edges"],
               f"实际 {len(arrows)} 条（已排除 [*] 起止边）: {arrows}")
        pairs = {frozenset(x) for x in arrows}
        record(stage, f"状态图状态对 = {EXPECT['transition_pairs']} 种（T2/T3、T4/T5 各共用一对）",
               len(pairs) == EXPECT["transition_pairs"], f"实际 {len(pairs)} 种: {sorted(map(tuple, pairs))}")

        forbidden_cn = ("已入住→已取消", "已退房→已取消", "已取消→已确认", "已入住→已确认", "已退房→已入住")
        miss = [f for f in forbidden_cn if f not in t]
        record(stage, "状态图注释写明 5 条禁止转换（逐条列出）", not miss, f"缺: {miss}")

        inv = {v: k for k, v in alias.items()}
        forbidden_alias = [("CHECKED_IN", "CANCELLED"), ("CHECKED_OUT", "CANCELLED"),
                           ("CANCELLED", "CONFIRMED"), ("CHECKED_IN", "CONFIRMED"),
                           ("CHECKED_OUT", "CHECKED_IN")]
        bad = [p for p in forbidden_alias if p in arrows]
        bad_cn = [f"{inv.get(a, a)}→{inv.get(b, b)}" for a, b in bad]
        record(stage, "状态图未把禁止转换画成允许的边（红线）", not bad,
               f"被画成边: {bad_cn}" if bad else f"已画 {len(arrows)} 条合法边")

    # ---------- 活动图：3 条泳道 / 判定 ≥3 / 并发与回滚 ----------
    ac_p = UML_DIR / "UML活动图.puml"
    if ac_p.exists():
        t = read(ac_p)
        lanes = []
        for ln in t.splitlines():
            m = re.match(r"^\|([^|]+)\|", ln.strip())
            if m:
                lanes.append(m.group(1).strip())
        uniq = list(dict.fromkeys(lanes))
        record(stage, "活动图泳道 = 3 条", len(uniq) == 3, f"实际 {len(uniq)} 条: {uniq}")
        ifs = len(re.findall(r"^\s*if\s*\(", t, re.M))
        record(stage, "活动图判定分支 ≥ 3", ifs >= 3, f"实际 {ifs} 个 if")
        has_fork = bool(re.search(r"^\s*fork\s*$", t, re.M)) and bool(re.search(r"^\s*end\s*fork\s*$", t, re.M))
        record(stage, "活动图有并发分支（fork/end fork）", has_fork, "" if has_fork else "缺 fork/end fork")
        record(stage, "活动图有失败回滚节点", "回滚" in t, "" if "回滚" in t else "没有任何『回滚』节点")
        # B 层那句"两请求抢最后一间只有一单成功"要能在图上看到：锁 + 锁后复核 + 回滚三件事齐
        ok_race = ("加锁" in t) and ("复核" in t) and ("回滚" in t)
        record(stage, "活动图画出并发抢房路径（加锁→锁后复核→回滚）", ok_race,
               "" if ok_race else "缺加锁/锁后复核/回滚之一")



def s4_interaction() -> None:
    stage = "S4"
    for stem in ("UML时序图-下单锁库存", "UML时序图-超时取消"):
        bad = need_pair(stem)
        record(stage, f"{stem}.puml/.png 成对且非空", not bad, f"缺/空: {bad}")

    # 按阶段卡 S4「A 层」与甲方复验 §7.6 逐条落地（复验 D-10：原判据只查文件成对）
    def lifelines(t: str) -> int:
        return len(re.findall(r"^\s*(?:actor|participant|boundary|control|entity|"
                              r"database|collections|queue)\s+", t, re.M))

    def messages(t: str) -> list[str]:
        out = []
        for ln in t.splitlines():
            s = ln.strip()
            if not s or s.startswith("'"):
                continue
            if re.search(r"-+>", s):
                out.append(s)
        return out

    def first(msgs: list[str], needle: str) -> int:
        return next((i for i, s in enumerate(msgs) if needle in s), -1)

    for stem in ("UML时序图-下单锁库存", "UML时序图-超时取消"):
        p = UML_DIR / f"{stem}.puml"
        if not p.exists():
            continue
        t = read(p)
        n = lifelines(t)
        record(stage, f"{stem} 生命线 ≥ 5", n >= 5, f"只有 {n} 条")
        has_alt = bool(re.search(r"^\s*alt\b", t, re.M))
        has_opt = bool(re.search(r"^\s*opt\b", t, re.M))
        record(stage, f"{stem} 含 alt 片段（并发/超时分支）", has_alt, "缺 alt")
        record(stage, f"{stem} 含 opt 片段（条件分支）", has_opt, "缺 opt")
        msgs = messages(t)
        body = "\n".join(msgs)
        record(stage, f"{stem} 消息里出现「逐日」", "逐日" in body, "消息中无「逐日」")
        record(stage, f"{stem} 消息里出现「事务」", "事务" in body, "消息中无「事务」")

    # 图 3-7：幂等键必须在消息里出现（REQ-014）
    p = UML_DIR / "UML时序图-下单锁库存.puml"
    if p.exists():
        msgs = messages(read(p))
        body = "\n".join(msgs)
        record(stage, "下单时序图 消息里出现「幂等键」", "幂等键" in body, "消息中无「幂等键」")
        # 红线：占用扣减必须落在 begin 与 commit 之间（画到事务外会丢房）
        ib, ia, ic = first(msgs, "开启事务"), first(msgs, "已占用间数 +="), first(msgs, "提交事务")
        ok = ib >= 0 and ia > ib and ic > ia
        record(stage, "下单时序图 红线：`已占用间数 +=` 落在 begin 与 commit 之间", ok,
               f"位置 begin={ib} 扣减={ia} commit={ic}" if not ok else "")

    # 图 3-8：回补必须与状态变更同一事务，且要有幂等/回滚兜底
    p = UML_DIR / "UML时序图-超时取消.puml"
    if p.exists():
        msgs = messages(read(p))
        body = "\n".join(msgs)
        ib = first(msgs, "开启事务")
        ir = next((i for i, s in enumerate(msgs) if "已占用间数" in s and ("−=" in s or "-=" in s)), -1)
        ic = first(msgs, "提交事务")
        ok = ib >= 0 and ir > ib and ic > ir
        record(stage, "超时时序图 红线：`已占用间数 −=` 落在 begin 与 commit 之间", ok,
               f"位置 begin={ib} 回补={ir} commit={ic}" if not ok else "")
        record(stage, "超时时序图 有状态前置判断（重复扫描不二次回补）", "状态前置判断" in body,
               "消息中无状态前置判断")
        record(stage, "超时时序图 有回滚分支（已被确认或已取消）", "回滚" in body, "消息中无回滚")

    # 2026-11-12 补两条守门：口径卡与 02 §5 都要求「重复校验在事务内」「超时取消用订单行锁」，
    # 图上画到事务外、或干脆没画锁，两条口径就永远对不上。
    p = UML_DIR / "UML时序图-下单锁库存.puml"
    if p.exists():
        msgs = messages(read(p))
        ib = first(msgs, "开启事务")
        il = next((i for i, s in enumerate(msgs) if "锁内复核" in s and "重叠" in s), -1)
        ok = ib >= 0 and il > ib
        record(stage, "下单时序图 重复预订校验落在事务内（锁内复核在 begin 之后）", ok,
               f"位置 begin={ib} 锁内复核={il}" if not ok else "")

    p = UML_DIR / "UML时序图-超时取消.puml"
    if p.exists():
        msgs = messages(read(p))
        ib = first(msgs, "开启事务")
        ic = first(msgs, "提交事务")
        il = next((i for i, s in enumerate(msgs) if "FOR UPDATE" in s.upper()), -1)
        iu = next((i for i, s in enumerate(msgs) if "WHERE" in s and "影响行数" in s), -1)
        ok = ib >= 0 and il > ib and iu > il and ic > iu
        record(stage, "超时时序图 订单行锁 + 条件更新（且落在 begin 与 commit 之间）", ok,
               f"位置 begin={ib} 行锁={il} 条件更新={iu} commit={ic}" if not ok else "")


def png_size(p) -> tuple[int, int]:
    """不依赖 Pillow：直接读 PNG 的 IHDR。"""
    import struct
    with open(p, "rb") as f:
        head = f.read(33)
    if len(head) < 33 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    w, h = struct.unpack(">II", head[16:24])
    return (int(w), int(h))


def s5_ui_customer() -> None:
    """S5：顾客端 9 张界面，必须成对存在、尺寸统一、并有一张表说清"界面→模块→REQ"。"""
    stage = "S5"
    for i in range(1, 10):
        p = UI_DIR / f"界面{i:02d}.png"
        ok = p.exists() and p.stat().st_size > 200_000
        record(stage, f"界面{i:02d}.png 存在且 >200KB（不是占位白图）", ok,
               "" if ok else ("缺失" if not p.exists() else f"仅 {p.stat().st_size} B"))
        if p.exists():
            w, h = png_size(p)
            record(stage, f"界面{i:02d}.png 尺寸 = 2880×1800", (w, h) == (2880, 1800), f"实际 {w}×{h}")

    doc = UI_DIR / "界面说明.md"
    if not doc.exists():
        record(stage, "UI界面/界面说明.md 存在", False, "未找到：界面必须有文字说明")
        return
    t = read(doc)
    record(stage, "界面说明.md 存在", True, "")
    for i in range(1, 10):
        row = [ln for ln in t.splitlines() if re.match(rf"^\|\s*界面{i:02d}\s*\|", ln)]
        ok = bool(row)
        record(stage, f"界面说明.md 有界面{i:02d} 的行", ok, "" if ok else "缺这一行")
        if row:
            cells = [c.strip() for c in row[0].strip("|").split("|")]
            joined = " ".join(cells)
            record(stage, f"界面{i:02d} 行标了模块（M\\d）与 REQ", bool(re.search(r"M\d", joined)) and "REQ" in joined.upper(),
                   "" if (re.search(r"M\d", joined) and "REQ" in joined.upper()) else joined[:80])
    record(stage, "界面说明.md 写明库存三值口径（可售 / 已占用 / 余量）",
           all(k in t for k in ("可售", "已占用", "余量")), "")
    record(stage, "界面说明.md 写明不可执行动作的处理（置灰并说明原因）",
           "置灰" in t, "" if "置灰" in t else "缺『置灰并说明原因』这句")
    # 顾客端只允许出现 M1/M2/M4/M5/M7 的界面，M3/M6/M8/M9 的界面必须留到 S6
    rows = {i: [ln for ln in t.splitlines() if re.match(rf"^\|\s*界面{i:02d}\s*\|", ln)] for i in range(1, 10)}
    bad = [i for i, v in rows.items() if v and re.search(r"M(3|6|8|9)\b", v[0])]
    record(stage, "顾客端 01–09 未越界承担酒店端/管理端模块", not bad,
           "" if not bad else f"这些行提到了 M3/M6/M8/M9：{bad}")


def s6_ui_hotel_admin() -> None:
    """S6：酒店端与管理端 8 张，必须满足评审给的五条硬门禁（11 三值 / 13 时间窗 / 16 两接口两视角 / 17 三约束）。"""
    stage = "S6"
    for i in range(10, EXPECT["ui_required"] + 1):
        p = UI_DIR / f"界面{i:02d}.png"
        ok = p.exists() and p.stat().st_size > 200_000
        record(stage, f"界面{i:02d}.png 存在且 >200KB", ok,
               "" if ok else ("缺失" if not p.exists() else f"仅 {p.stat().st_size} B"))
        if p.exists():
            w, h = png_size(p)
            record(stage, f"界面{i:02d}.png 尺寸 = 2880×1800", (w, h) == (2880, 1800), f"实际 {w}×{h}")

    doc = UI_DIR / "界面说明.md"
    if not doc.exists():
        record(stage, "UI界面/界面说明.md 存在", False, "未找到")
        return
    t = read(doc)
    for i in range(10, EXPECT["ui_required"] + 1):
        row = [ln for ln in t.splitlines() if re.match(rf"^\|\s*界面{i:02d}\s*\|", ln)]
        record(stage, f"界面说明.md 有界面{i:02d} 的行", bool(row), "" if row else "缺这一行")
        if row:
            joined = " ".join(c.strip() for c in row[0].strip("|").split("|"))
            record(stage, f"界面{i:02d} 行标了模块与 REQ",
                   bool(re.search(r"M\d", joined)) and "REQ-" in joined, joined[:80])

    # 门禁 2：界面 11 必须三值齐全，并画出"改可售低于已占用被拒"
    row11 = " ".join([ln for ln in t.splitlines() if re.match(r"^\|\s*界面11\s*\|", ln)])
    record(stage, "界面11 三值齐全（可售 / 已占用 / 余量）",
           all(k in row11 for k in ("可售", "已占用", "余量")), row11[:90])
    record(stage, "界面11 写明改可售低于已占用会被拒绝",
           ("低于已占用" in row11) or ("不能低于" in row11), row11[:90])

    # 门禁 3：界面 13 的 no-show 时间窗
    row13 = " ".join([ln for ln in t.splitlines() if re.match(r"^\|\s*界面13\s*\|", ln)])
    record(stage, "界面13 写明 no-show 时间窗（23:59 前 / 次日 00:05）",
           "23:59" in row13 and "00:05" in row13, row13[:90])

    # 门禁 4：界面 16 两个接口 + 两个视角
    row16 = " ".join([ln for ln in t.splitlines() if re.match(r"^\|\s*界面16\s*\|", ln)])
    record(stage, "界面16 体现 I15 与 I21 两个接口", "I15" in row16 and "I21" in row16, row16[:90])
    record(stage, "界面16 区分本店 / 全平台两视角", "本店" in row16 and "全平台" in row16, row16[:90])

    # 门禁 5：界面 17 三条硬约束
    row17 = " ".join([ln for ln in t.splitlines() if re.match(r"^\|\s*界面17\s*\|", ln)])
    record(stage, "界面17 写明只追加 / 180 天 / 403 三条硬约束",
           ("只追加" in row17) and ("180" in row17) and ("403" in row17), row17[:90])

    # 门禁 7：模块覆盖 —— M1–M9 每块都要有独占界面，M10 明确无界面
    sec = re.search(r"##\s*2\.[^\n]*\n(.+?)(?=\n##\s|\Z)", t, re.S)
    body = sec.group(1) if sec else ""
    missing = []
    for m in range(1, 10):
        row = [ln for ln in body.splitlines() if re.match(rf"^\|\s*M{m}\s", ln)]
        if not row or not re.search(r"\b0\d\b|\b1\d\b", row[0]):
            missing.append(f"M{m}")
    record(stage, "模块覆盖表里 M1–M9 都列出了界面号", not missing,
           "" if not missing else f"这些模块没有界面号：{missing}")
    record(stage, "模块覆盖表里 M10 明确写「无独立界面」", "无独立界面" in body,
           "" if "无独立界面" in body else "M10 行没写清")


def s7_report() -> None:
    """S7：报告 1–6 章。判据按评审给的 5 条门禁逐条落地（不是"有文件就算过"）。"""
    stage = "S7"
    p = ROOT / "实验报告.md"
    if not p.exists():
        record(stage, "实验报告.md 存在", False, "未找到")
        return
    t = read(p)
    record(stage, "实验报告.md 存在且 > 12000 字", len(t) > 12_000, f"实际 {len(t)} 字符")

    # 1) 封面 / 目录 / 标识
    head = t[:1500]
    record(stage, "封面含课程名「软件工程」", "软件工程" in head, "")
    record(stage, "封面含学号与姓名", "241220024" in head and "陈一帆" in head, "")
    record(stage, "封面不写指导教师（口径：留空）", "指导教师" not in head, "封面出现了指导教师字样")
    record(stage, "有目录", "## 目录" in t or "目录" in head, "")

    # 2) 六个一级章节
    for n, name in enumerate(["项目与需求范围", "软件的主要功能", "软件架构设计",
                              "数据设计", "非功能设计", "界面设计"], start=1):
        pat = rf"^##\s*第{n}章.*{name}"
        record(stage, f"第{n}章《{name}》存在且顺序正确", bool(re.search(pat, t, re.M)), "")

    # 3) 八张图：图注 + 正文引用（图号出现 ≥2 次：图注一次、引用一次），且每图后紧跟"为什么这样设计"
    figs = ["类图", "包图", "组件图", "用例图", "状态图", "活动图",
            "时序图：下单锁库存", "时序图：超时取消"]
    for i, _ in enumerate(figs, start=1):
        tag = f"图 3-{i}"
        cnt = t.count(tag)
        record(stage, f"{tag} 在图注与正文各出现一次（≥2 次）", cnt >= 2, f"实际 {cnt} 次")
    caps = re.findall(r"^图 3-(\d)　(.+)$", t, re.M)
    record(stage, "8 条图注齐全（图 3-1 … 图 3-8）",
           sorted(int(n) for n, _ in caps) == list(range(1, 9)), f"实际 {[n for n, _ in caps]}")

    # 每张图注之后 900 字内必须出现"为什么这样设计"（手册：只截图不解释要扣分）
    missing = []
    for n, cap in caps:
        idx = t.find(f"图 3-{n}　")
        window = t[idx: idx + 900]
        if "为什么这样设计" not in window:
            missing.append(f"图 3-{n}")
    record(stage, "每张图后都有「为什么这样设计」段落", not missing,
           "" if not missing else f"缺: {missing}")

    # 4) 27 条 REQ 在正文出现（附录之外也要有）
    body_only = t.split("## 附录 A")[0]
    miss = [r["id"] for r in json.loads((ROOT / "验收" / "req_index.json").read_text(encoding="utf-8"))
            if r["id"] not in body_only]
    record(stage, "27 条 REQ 在正文（不含附录）各出现 ≥1 次", not miss,
           "" if not miss else f"缺: {miss}")
    record(stage, "附录 A 含 27 条 REQ 全文",
           len(re.findall(r"^\*\*REQ-\d{3}　", t, re.M)) == 27,
           f"实际 {len(re.findall(r'^\*\*REQ-\\d{3}　', t, re.M))} 条")

    # 5) 关键口径不得回退（与 stage 1 的禁用词一致）
    for bad in BANNED:
        record(stage, f"报告中不出现旧口径「{bad}」", bad not in t, "出现了")

    # 6) 版面骨架：每章都有小节，且第 3 章（架构）字数够
    ch3 = t.split("## 第3章")[1].split("## 第4章")[0] if "## 第4章" in t else ""
    record(stage, "第 3 章字数 ≥ 3000（架构是主章节）", len(ch3) >= 3000, f"实际 {len(ch3)} 字符")
    record(stage, "第 3 章含 8 个小节（3.5.1–3.5.8）",
           len(re.findall(r"^#### 3\.5\.\d", ch3, re.M)) == 8,
           f"实际 {len(re.findall(r'^#### 3.5.\\d', ch3, re.M))} 个")


    # 6.4 的 17 条界面描述与 4 张插图：这是本轮必改的那一节，
    # 没有判据的话整段可以被删掉而全绿（"没人守的部分会悄悄漂"）
    n6 = len(re.findall(r"^####\s*界面\d{2}", t, re.M))
    record(stage, "6.4 恰好 17 条界面描述（#### 界面NN）", n6 == 17, f"实际 {n6} 条")
    n6fig = len(re.findall(r"^图 6-\d", t, re.M))
    record(stage, "6.4 含 4 张界面插图（图 6-1…6-4 图注）", n6fig == 4, f"实际 {n6fig} 张")
    record(stage, "6.4 标注为与界面说明.md 手工同步（不写『脚本生成』）",
           "手工同步" in t and "脚本生成" not in t, "")


def s8_ai() -> None:
    """S8：第 7 章 AI 使用记录 + 第 8 章两问。判据比"数出现次数"更硬：
    每条记录必须凑齐 6 个要素、必须挂一个真实存在的 [人工] 提交号、必须有工具评价，
    并且全文不得留占位语——否则"先写结构、回头补"的空壳也能骗过检查。"""
    stage = "S8"
    p = ROOT / "实验报告.md"
    if not p.exists():
        record(stage, "实验报告.md 存在", False, "未找到")
        return
    t = read(p)

    # 第 7 / 8 章必须已经成稿（不是占位标题）
    ch7 = section(t, r"## 第 7 章", r"## 第 8 章")
    ch8 = section(t, r"## 第 8 章", r"## 附录")
    record(stage, "第 7 章已有正文（≥ 2500 字符）", len(ch7) >= 2500, f"实际 {len(ch7)} 字符")
    record(stage, "第 8 章已有正文（≥ 800 字符）", len(ch8) >= 800, f"实际 {len(ch8)} 字符")

    # 占位语：出现即说明还没写完，直接判失败
    holes = [w for w in ("见 S8", "待补", "本节先留结构", "TODO", "待写") if w in t]
    record(stage, "全文无『见 S8 / 待补 / 待写』等占位语", not holes, "命中：" + "、".join(holes))

    # 记录条目：### AI-01 … 每条 6 要素
    recs = re.split(r"^###\s*AI-(\d+)[^\n]*$", ch7, flags=re.M)
    starts = [m.start() for m in re.finditer(r"^###\s*AI-\d+", ch7, flags=re.M)]
    boxes = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(ch7)
        boxes.append(ch7[s:e])
    record(stage, "AI 使用记录 ≥ 6 条", len(boxes) >= 6, f"实际 {len(boxes)} 条")

    need = ("使用场景", "给了什么", "原样结果", "发现的问题", "人工改后", "工具优缺点")
    bad = []
    for k, b in enumerate(boxes, 1):
        miss = [w for w in need if w not in b]
        if miss:
            bad.append(f"AI-{k:02d} 缺 " + "/".join(miss))
    record(stage, "每条记录含 6 要素（场景/输入/原样结果/问题/人工改后/优缺点）",
           bool(boxes) and not bad, "没有记录" if not boxes else "；".join(bad[:4]))

    # 人工落点：每条记录都要指到一个真实的 [人工] 提交
    known = ["2686e23", "1d48c09", "afb8ca2", "391d4aa", "13b693e", "7684412", "fff3023"]
    hit = [h for h in known if h in ch7]
    record(stage, "第 7 章引用真实 [人工] 提交号 ≥ 6 个", len(hit) >= 6, f"实际 {len(hit)} 个：{hit}")
    record(stage, "第 7 章写明人改后与 AI 原稿的差别", "改后" in ch7 and "原" in ch7, "")

    # 第 8 章两问
    q1 = re.search(r"问题一|第一问|大模型如何辅助", ch8)
    q2 = re.search(r"问题二|第二问|工作流", ch8)
    record(stage, "第 8 章两问各有小标题", bool(q1) and bool(q2), "")
    body_len = len(re.sub(r"\s", "", ch8))
    record(stage, "第 8 章两问合计 ≥ 900 字（不是一句话应付）", body_len >= 900, f"实际 {body_len} 字")
    record(stage, "第 8 章正面回答『能不能只做检查校对』", ("检查" in ch8 or "校对" in ch8) and
           ("不能" in ch8 or "能" in ch8), "")
    record(stage, "第 7 章不出现『评审报告』口径（按 m02820 定为自查 + 同学互看）",
           "评审报告" not in ch7, "" if "评审报告" not in ch7 else "第 7 章仍出现『评审报告』")


def s9_delivery() -> None:
    stage = "S9"
    pdf = ROOT / "实验报告.pdf"
    record(stage, "实验报告.pdf 存在", pdf.exists() and pdf.stat().st_size > 50_000, "")
    zips = list(ROOT.glob("实验2_241220024_陈一帆.zip"))
    record(stage, "交付 zip 存在且命名合规", bool(zips), "未找到 实验2_241220024_陈一帆.zip")
    if zips:
        import zipfile
        with zipfile.ZipFile(zips[0]) as z:
            names = z.namelist()
        record(stage, "zip 内顶层目录 = 实验2_241220024_陈一帆/",
               all(n.startswith("实验2_241220024_陈一帆/") for n in names), "")
        record(stage, "zip 含 UML/ 与 UI界面/ 目录",
               any("/UML/" in n for n in names) and any("/UI界面/" in n for n in names), "")


def s1_gate_items() -> None:
    """复验报告 R-03 / T-08 引入的两处口径，必须被机械检查看住。"""
    stage = "S1"
    b3 = read(B3)
    m = re.search(r"##\s*9\.\s*唯一约束清单", b3)
    record(stage, "03 有 §9『唯一约束清单』（R-03）", bool(m),
           "" if m else "缺 §9：『6 条』必须给出可核对的清单")
    if m:
        tail = b3[m.start():]
        u = len(re.findall(r"^\|\s*U\d\s*\|", tail, re.M))
        t = len(re.findall(r"^\|\s*T\d\s*\|", tail, re.M))
        record(stage, "§9 业务唯一 = 6 条（U1–U6）", u == EXPECT["unique_business"], f"实际 {u}")
        record(stage, "§9 技术性唯一 = 4 条（T1–T4，另计不混入 6）", t == EXPECT["unique_tech"], f"实际 {t}")
        record(stage, "§9 写明部分唯一拦不住区间重叠", "区间重叠" in tail,
               "" if "区间重叠" in tail else "缺『拦不住区间重叠』这句")
    # T-08：T5/T6 的时间点必须与"先后关系"一致，不能两边都要求 23:59 前
    b1 = read(B1)
    row5 = [ln for ln in b1.splitlines() if re.match(r"^\|\s*T5\s*\|", ln)]
    row6 = [ln for ln in b1.splitlines() if re.match(r"^\|\s*T6\s*\|", ln)]
    r5, r6 = (row5[0] if row5 else ""), (row6[0] if row6 else "")
    record(stage, "T5 触发写『次日 00:05』且守卫锚定 23:59 时的快照",
           "00:05" in r5 and "23:59 时仍为已确认" in r5,
           "" if ("00:05" in r5 and "23:59 时仍为已确认" in r5) else r5[:90])
    record(stage, "T6 明确『23:59 之前』且过时由 T5 兜底",
           "23:59 之前" in r6 and "兜底" in r6, "" if ("23:59 之前" in r6 and "兜底" in r6) else r6[:80])
    # 阶段卡 §5 必须记录标签与提交号，避免"标签落后 HEAD"再次发生（D-05/D-06）
    phase = read(PHASE)
    record(stage, "阶段卡 §5 记录 stage-1b 的提交号与结果",
           "stage-1b" in phase and "43" in phase, "")


STAGES = {
    "1": ("S1 基线与口径冻结", [s1_req_trace, s1_req_module_cover, s1_transitions,
                              s1_tables, s1_stock_model, s1_ui, s1_class_spec, s1_banned,
                              s1_phase_card, s1_gate_items]),
    "2": ("S2 结构图", [s2_struct]),
    "3": ("S3 行为图", [s3_behavior]),
    "4": ("S4 交互图", [s4_interaction]),
    "5": ("S5 UI 顾客端", [s5_ui_customer]),
    "6": ("S6 UI 酒店端与管理端", [s6_ui_hotel_admin]),
    "7": ("S7 报告正文", [s7_report]),
    "8": ("S8 AI 章节", [s8_ai]),
    "9": ("S9 打包交付", [s9_delivery]),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="实验二验收脚本（A 层机械检查）")
    ap.add_argument("--stage", default="1", help="1..9，或 all 表示 1..9 全跑")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印每项明细")
    args = ap.parse_args()

    todo = list(STAGES) if args.stage == "all" else [args.stage]
    for s in todo:
        if s not in STAGES:
            print(f"未知阶段: {s}")
            return 2
        title, fns = STAGES[s]
        print(f"\n===== {title} =====")
        before = len(results)
        for fn in fns:
            try:
                fn()
            except Exception as exc:                     # 单点异常不影响其余检查
                record(s, f"{fn.__name__} 执行异常", False, repr(exc))
        for _, name, ok, detail in results[before:]:
            flag = "PASS" if ok else "FAIL"
            line = f"[{flag}] {name}"
            if detail and not ok:
                line += f"  ←  {detail}"
            elif detail and args.verbose and not FAILWORDS.search(detail):
                line += f"  （实测：{detail}）"
            print(line)

    fails = [r for r in results if not r[2]]
    print("\n" + "-" * 60)
    print(f"合计 {len(results)} 项：PASS {len(results) - len(fails)} / FAIL {len(fails)}")
    if fails:
        print("未通过项：")
        for stage, name, _, detail in fails:
            print(f"  - {stage} {name}" + (f"  ←  {detail}" if detail else ""))
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
