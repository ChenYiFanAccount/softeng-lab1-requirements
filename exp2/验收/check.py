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
    hits = []
    for p in [B1, B2, B3, PLAN]:
        for i, ln in enumerate(lines_of(p), 1):
            for word in BANNED:
                if word in ln:
                    hits.append(f"{p.name}:{i} 命中『{word}』")
    record(stage, "禁用词零命中（旧口径残留）", not hits,
           "；".join(hits) if hits else f"扫描 {len(BANNED)} 个禁用词，4 份文档干净")


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
def need_pair(stem: str) -> list[str]:
    bad = []
    for ext in (".puml", ".png"):
        p = UML_DIR / f"{stem}{ext}"
        if not p.exists() or p.stat().st_size < 200:
            bad.append(f"{p.name}")
    return bad


def s2_struct() -> None:
    stage = "S2"
    for stem in ("UML类图", "UML包图", "UML组件图"):
        bad = need_pair(stem)
        record(stage, f"{stem}.puml/.png 成对且非空", not bad, f"缺/空: {bad}")
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


def s3_behavior() -> None:
    stage = "S3"
    for stem in ("UML用例图", "UML状态图", "UML活动图"):
        bad = need_pair(stem)
        record(stage, f"{stem}.puml/.png 成对且非空", not bad, f"缺/空: {bad}")
    p = UML_DIR / "UML状态图.puml"
    if p.exists():
        t = read(p)
        arrows = []
        for ln in t.splitlines():
            m = re.search(r"^\s*(\S+)\s*-->\s*(\S+)", ln)
            if not m:
                continue
            a, b = m.group(1), m.group(2)
            # [*] 是起止伪状态，不是六状态之间的转换；进出 [*] 的边不计入 8 条
            if a.startswith("[*]") or b.startswith("[*]"):
                continue
            arrows.append((a, b))
        record(stage, f"状态图转换边 = {EXPECT['transition_edges']}", len(arrows) == EXPECT["transition_edges"],
               f"实际 {len(arrows)} 条（已排除 [*] 起止边）: {arrows}")


def s4_interaction() -> None:
    stage = "S4"
    for stem in ("UML时序图-下单锁库存", "UML时序图-超时取消"):
        bad = need_pair(stem)
        record(stage, f"{stem}.puml/.png 成对且非空", not bad, f"缺/空: {bad}")


def s5_ui_customer() -> None:
    stage = "S5"
    for i in range(1, 10):
        p = UI_DIR / f"界面{i:02d}.png"
        ok = p.exists() and p.stat().st_size > 20_000
        record(stage, f"界面{i:02d}.png 存在且非空", ok, "" if ok else "缺失或过小")


def s6_ui_hotel_admin() -> None:
    stage = "S6"
    for i in range(10, EXPECT["ui_required"] + 1):
        p = UI_DIR / f"界面{i:02d}.png"
        ok = p.exists() and p.stat().st_size > 20_000
        record(stage, f"界面{i:02d}.png 存在且非空", ok, "" if ok else "缺失或过小")


def s7_report() -> None:
    stage = "S7"
    p = ROOT / "实验报告.md"
    if not p.exists():
        record(stage, "实验报告.md 存在", False, "未找到")
        return
    t = read(p)
    record(stage, "含 6 个一级章节骨架", len(re.findall(r"^## ", t, re.M)) >= 6, "")
    record(stage, "正文引用 UML 图（图 3-x）", len(re.findall(r"图\s*3-\d", t)) >= 3, "")
    record(stage, "正文引用界面编号", len(re.findall(r"界面\s*\d{2}", t)) >= 5, "")


def s8_ai() -> None:
    stage = "S8"
    p = ROOT / "实验报告.md"
    if not p.exists():
        record(stage, "实验报告.md 存在", False, "未找到")
        return
    t = read(p)
    n = len(re.findall(r"^### AI-\d+", t, re.M))
    record(stage, "AI 使用记录 ≥ 6 条", n >= 6, f"实际 {n} 条")
    for field in ("使用场景", "生成结果", "优缺点", "修改优化"):
        record(stage, f"每条记录含『{field}』字段", t.count(field) >= 6, f"出现 {t.count(field)} 次")
    record(stage, "章末两问均有回答", "工作流" in t and ("检查" in t or "校对" in t), "")


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


STAGES = {
    "1": ("S1 基线与口径冻结", [s1_req_trace, s1_req_module_cover, s1_transitions,
                              s1_tables, s1_stock_model, s1_ui, s1_class_spec, s1_banned, s1_phase_card]),
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
