"""生成实验三报告 DOCX。

运行：python exp3/build_report_v2.py
输出：exp3/交付包/实验3_241220024_陈一帆/实验报告.docx
"""

from __future__ import annotations

import pathlib

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = pathlib.Path(__file__).resolve().parent
STAGE = ROOT / "交付包" / "实验3_241220024_陈一帆"
SHOTS = ROOT / "tmp_shots"
UML = STAGE / "UML"

BODY_FONT = "宋体"
HEAD_FONT = "黑体"
MONO_FONT = "Consolas"

STUDENT_ID = "241220024"
STUDENT_NAME = "陈一帆"


def set_font(run, name=BODY_FONT, size=10.5, bold=False):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def style_document(document):
    normal = document.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.line_spacing = 1.35
    normal.paragraph_format.space_after = Pt(4)

    for name, size in (("Heading 1", 16), ("Heading 2", 13)):
        style = document.styles[name]
        style.font.name = HEAD_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.element.rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT)
        style.paragraph_format.space_before = Pt(12 if name == "Heading 1" else 8)
        style.paragraph_format.space_after = Pt(6)

    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.6)
    section.right_margin = Cm(2.6)
    section.top_margin = Cm(2.4)
    section.bottom_margin = Cm(2.2)


def para(document, text, indent=True, size=10.5, bold=False):
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Cm(0.74) if indent else Cm(0)
    set_font(paragraph.add_run(text), size=size, bold=bold)
    return paragraph


def bullet(document, text):
    paragraph = document.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.left_indent = Cm(0.74)
    paragraph.paragraph_format.space_after = Pt(2)
    set_font(paragraph.add_run(text))


def caption(document, text):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(8)
    set_font(paragraph.add_run(text), size=9)


def code_block(document, text):
    for line in text.strip("\n").split("\n"):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.6)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.05
        set_font(paragraph.add_run(line), name=MONO_FONT, size=9)


def table(document, header, rows, widths=None):
    grid = document.add_table(rows=1, cols=len(header))
    grid.style = "Table Grid"
    grid.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, text in enumerate(header):
        cell = grid.rows[0].cells[index]
        cell.text = ""
        set_font(cell.paragraphs[0].add_run(text), size=9, bold=True)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for row in rows:
        cells = grid.add_row().cells
        for index, text in enumerate(row):
            cells[index].text = ""
            set_font(cells[index].paragraphs[0].add_run(str(text)), size=9)
    if widths:
        for row in grid.rows:
            for index, width in enumerate(widths):
                row.cells[index].width = Cm(width)
    document.add_paragraph().paragraph_format.space_after = Pt(2)
    return grid


def picture(document, path, width_cm, cap):
    if not path.exists():
        para(document, "（缺图：" + path.name + "）", indent=False, size=9)
        return
    document.add_picture(str(path), width=Cm(width_cm))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption(document, cap)


def page_break(document):
    document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def build_cover(document):
    for _ in range(3):
        document.add_paragraph()

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(title.add_run("软件工程实践 · 实验三"), size=15, bold=True)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_before = Pt(10)
    set_font(subtitle.add_run("软件实现与构建"), name=HEAD_FONT, size=26, bold=True)

    document.add_paragraph()
    app = document.add_paragraph()
    app.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(app.add_run("—— 酒店预订管理系统 ——"), name=HEAD_FONT, size=14)

    for _ in range(4):
        document.add_paragraph()

    info = [
        ("课程", "软件工程实践"),
        ("实验", "实验三　软件实现与构建"),
        ("项目", "酒店预订管理系统（Python 3.12 + Tkinter + SQLite）"),
        ("学号", STUDENT_ID),
        ("姓名", STUDENT_NAME),
        ("日期", "2026 年 11 月 26 日"),
    ]
    grid = document.add_table(rows=0, cols=2)
    grid.alignment = WD_TABLE_ALIGNMENT.CENTER
    for key, value in info:
        cells = grid.add_row().cells
        cells[0].width = Cm(3.2)
        cells[1].width = Cm(9.0)
        set_font(cells[0].paragraphs[0].add_run(key), size=11, bold=True)
        cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        set_font(cells[1].paragraphs[0].add_run(value), size=11)

    page_break(document)


def build_toc(document):
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(heading.add_run("目　录"), name=HEAD_FONT, size=18, bold=True)
    document.add_paragraph()

    entries = [
        ("1　实现概述：从 UML 到代码", 0),
        ("1.1　分层与模块落地", 1),
        ("1.2　类图 19 个符号的落点", 1),
        ("1.3　十屏界面与运行入口", 1),
        ("2　源码规模与度量", 0),
        ("2.1　有效代码行的口径与结果", 1),
        ("2.2　测试、覆盖率与静态检查", 1),
        ("3　大模型如何参与开发", 0),
        ("3.1　两类角色：执行者与评审人", 1),
        ("3.2　八条真实记录", 1),
        ("3.3　边界：哪些事不让大模型做", 1),
        ("4　让大模型做了什么", 0),
        ("4.1　功能代码生成", 1),
        ("4.2　单元测试与模拟用户测试", 1),
        ("4.3　风格检查与坏味道消除", 1),
        ("4.4　文档与证据整理", 1),
        ("5　不符合预期时怎么做", 0),
        ("5.1　案例一：事务与并发", 1),
        ("5.2　案例二：状态机边数口径", 1),
        ("5.3　案例三：截图只拍到窗口左边三分之二", 1),
        ("5.4　案例四：退房后营收归零", 1),
        ("6　编译与运行结果", 0),
        ("6.1　编译与建库", 1),
        ("6.2　核心判据的实测输出", 1),
        ("6.3　界面运行结果", 1),
        ("7　Git 本地仓库与远程托管", 0),
        ("7.1　分支与合并策略", 1),
        ("7.2　标签与提交节奏", 1),
        ("7.3　远程仓库", 1),
        ("8　质量自查与遗留问题", 0),
        ("9　结论与体会", 0),
        ("附录 A　复跑命令清单", 0),
        ("附录 B　R1–R6 与本书章节对照", 0),
        ("附录 C　参考文献", 0),
    ]
    for text, level in entries:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.8 * level)
        paragraph.paragraph_format.space_after = Pt(2)
        set_font(paragraph.add_run(text), size=10.5, bold=level == 0)
    page_break(document)


def chapter_1(document):
    document.add_paragraph("1　实现概述：从 UML 到代码", style="Heading 1")

    para(
        document,
        "本实验要把实验二的设计变成能跑起来的程序。实验二交付的类图共 19 个符号："
        "12 个实体（含 1 个枚举）、3 个领域服务、3 个仓储接口；数据设计给出 12 张表、"
        "6 条业务唯一与 4 条技术唯一约束；模块划分给出 4 层架构与 M1–M10 十条纵切。"
        "实现阶段没有推翻这些设计，而是逐条落到目录、类名、SQL 与用例上。",
    )

    document.add_paragraph("1.1　分层与模块落地", style="Heading 2")
    para(
        document,
        "代码分四层，依赖方向单一：界面层只调用应用服务，应用服务组合领域对象与仓储接口，"
        "数据访问层实现仓储接口。唯一一处反向箭头是领域层定义仓储接口、数据访问层实现它；"
        "这是让领域层不依赖 sqlite3 的必要代价，已在类图与追溯表中标注。",
    )
    table(
        document,
        ["层", "目录", "职责", "文件数"],
        [
            ["领域层", "code/app/domain/", "12 实体、状态机、计价、库存规则、仓储接口", "11"],
            ["应用层", "code/app/application/", "下单/取消/改期、履约扫描、报表、对账、账号、审核", "12"],
            ["数据访问层", "code/app/infrastructure/db/", "12 表 DDL、迁移、连接与事务、仓储实现、种子", "16"],
            ["界面层", "code/app/ui/", "十屏 Tkinter 界面、会话与服务工厂", "19"],
        ],
        widths=[2.0, 5.0, 6.6, 1.6],
    )
    caption(document, "表 1-1　四层结构与代码落点（文件数含 __init__.py）")

    document.add_paragraph("1.2　类图 19 个符号的落点", style="Heading 2")
    para(
        document,
        "为保证图与码不脱节，写了一个校验工具 check_uml_sync.py：读取 puml 里的 as 别名、"
        "扫描 code/app 下的类定义、再对照 code/docs/uml_map.md 的白名单，"
        "输出缺失符号与行号是否漂移。当前结果：19 个符号全部命中，两个差集都为空。",
    )
    table(
        document,
        ["类别", "符号", "代码落点"],
        [
            ["实体 12", "UserAccount / Hotel / RoomType / RoomInventory / RoomPrice / Booking / BookingNight / IdempotencyKey / StayRecord / AuditLog / NotificationRecord / HolidayCalendar", "domain/models.py"],
            ["枚举 1", "BookingStatus（六状态）", "domain/enums.py"],
            ["领域服务 3", "BookingStateMachine / BookingService / InventoryService", "domain/state_machine.py、domain/services.py"],
            ["仓储接口 3", "BookingRepository / InventoryRepository / AuditLogRepository", "domain/repositories.py"],
        ],
        widths=[2.2, 8.4, 4.6],
    )
    caption(document, "表 1-2　19 个设计符号的实现落点")
    picture(document, UML / "UML类图.png", 15.0, "图 1-1　实验二类图（实现按此逐符号对齐）")

    document.add_paragraph("1.3　十屏界面与运行入口", style="Heading 2")
    para(
        document,
        "界面共十屏，按先顾客、后店家、再平台的依赖顺序排列：登录注册、酒店搜索、搜索结果、"
        "我的订单、酒店订单台、库存与房价、审计日志、库存对账、平台管理、经营报表。"
        "界面层不写 SQL，全部通过应用服务；这一点由 check_source_rules.py 与人工扫描双重验证"
        "（code/app/ui 内 SELECT、INSERT、UPDATE 命中 0）。入口是 code/run.py，缺库时自动建表并写种子。",
    )
    table(
        document,
        ["屏", "key", "谁能进", "主要动作"],
        [
            ["1 登录注册", "login", "全部", "登录、登出、注册顾客"],
            ["2 酒店搜索", "search", "全部", "关键词、入住日、退房日"],
            ["3 搜索结果", "results", "顾客", "选房型、填间数与幂等键、提交订单"],
            ["4 我的订单", "my_orders", "顾客", "看详情、取消、改期一晚"],
            ["5 酒店订单台", "hotel_console", "店长/管理员", "确认、拒单、入住、退房、未入住"],
            ["6 库存与房价", "inventory", "店长", "改可售、改价、停售、复售"],
            ["7 审计日志", "audit", "店长/管理员", "按对象类型与 ID 查审计"],
            ["8 库存对账", "reconcile", "店长/管理员", "选天数、立即对账、看差异"],
            ["9 平台管理", "admin", "管理员", "酒店审核、账号只读列表"],
            ["10 经营报表", "reports", "店长/管理员", "入住率、营收、订单状态三页签"],
        ],
        widths=[3.4, 2.8, 3.0, 6.0],
    )
    caption(document, "表 1-3　十屏界面清单（与 ui_smoke.py 的 screen_names 一致）")


def chapter_2(document):
    document.add_paragraph("2　源码规模与度量", style="Heading 1")

    document.add_paragraph("2.1　有效代码行的口径与结果", style="Heading 2")
    para(
        document,
        "手册要求代码量超过 1500 行，且 GUI 设计工具自动生成的代码不计。本项目没有使用"
        ".ui 或 .designer 文件，界面代码全部手写，因此不存在自动生成代码需要剔除的问题；"
        "但为了让 1500 行这个数字站得住，仍然自己写了统计工具 count_loc.py，同时给出三列："
        "物理行、非空非注释行、有效行（再扣掉 docstring，用 ast 判定）。"
        "主口径取有效行，且只统计 code/app，测试与工具单列，不混算。",
    )
    table(
        document,
        ["范围", "文件数", "物理行", "非空非注释", "有效行"],
        [
            ["code/app（主口径）", "57", "7405", "6152", "5054"],
            ["code/tests", "22", "—", "—", "2504"],
            ["code/tools", "12", "—", "—", "1713"],
            ["合计", "91", "—", "—", "9271"],
        ],
        widths=[4.6, 2.0, 2.6, 3.0, 3.0],
    )
    caption(document, "表 2-1　代码规模（count_loc.py --per-file，逐文件明细见 code/docs/loc.csv）")
    para(
        document,
        "主口径 5054 行，是手册下限 1500 行的 3.4 倍。之所以没有停在 1500 行附近，"
        "是因为判据里还有状态机 13 条边、200 线程不超卖、越权不泄露存在性、十屏界面这些要求，"
        "它们本身就带来大量真实代码；反过来也没有为凑行数写废话，被扣掉的 1351 行空行、"
        "注释与 docstring 就是证据。",
    )

    document.add_paragraph("2.2　测试、覆盖率与静态检查", style="Heading 2")
    table(
        document,
        ["项目", "结果", "命令"],
        [
            ["单元测试", "152 条用例全绿（3 秒级）", "python -m unittest discover -s code/tests -t code"],
            ["断言数", "406 条（静态计数）", "证据 S7_03b"],
            ["语句覆盖率", "92%（1159 语句、未覆盖 68、分支 198、部分分支 23）", "coverage run --branch -m unittest"],
            ["静态检查", "pylint 10.00 分、0 条消息", "python -m pylint code/app --rcfile=code/.pylintrc"],
            ["源码规则", "5 条规则命中 0", "python code/tools/check_source_rules.py"],
            ["图码一致", "19 符号双向零缺失", "python code/tools/check_uml_sync.py"],
            ["并发", "成功 1、失败 199、锁错误 0、负库存 0", "python code/tools/concurrency_probe.py --threads 200 --rooms 1"],
        ],
        widths=[2.6, 8.6, 6.4],
    )
    caption(document, "表 2-2　质量度量（完整输出见 code/docs/evidence/）")
    para(
        document,
        "覆盖率只统计领域层与应用层（判据也只要求这两层）。92% 里没覆盖到的 68 行集中在异常分支"
        "与理论上到不了的兜底；测试文件本身不计入分母。pylint 的 14 条行内 disable 全部是"
        "实体字段镜像表列、领域服务建单六要素必填这类结构性理由，每条都写了中文原因，"
        "且 0 条 error 级。",
    )


def chapter_3(document):
    document.add_paragraph("3　大模型如何参与开发", style="Heading 1")

    document.add_paragraph("3.1　两类角色：执行者与评审人", style="Heading 2")
    para(
        document,
        "本实验对大模型的使用不是问一句、抄一段，而是搭了一个双角色流程：执行者负责写代码、"
        "跑命令、生成证据；评审人只读仓库、独立复跑、出通过或不通过的判定。两者之间有一份章程，"
        "规定阶段划分、门禁批次、判定三态（通过、有条件通过、不通过）、证据标准与红线。"
        "评审人不能改代码，执行者不能自己宣布通过。这条约束在本次实验里起了实质作用，"
        "至少拦下 6 个看起来完成了、其实不成立的结论。",
    )
    para(
        document,
        "节奏是：每个阶段（S0 到 S9）执行者先交一份交付说明（做了什么、证据、偏差、规模、复跑命令），"
        "评审人独立跑一遍判据、核对数字、写评审意见；不通过就整改，整改完再复核。"
        "门禁按批次合并：G1 含 S0 到 S2、G2 含 S3、G3 含 S4 与 S5、G4 含 S6、G5 含 S7 到 S9。",
    )

    document.add_paragraph("3.2　八条真实记录", style="Heading 2")
    para(
        document,
        "按手册要求，记录了 8 次有代表性的交互，覆盖代码生成、单元测试设计、模拟用户测试、"
        "风格检查、坏味道消除五类场景。每条记录的完整版（输入、输出摘要、问题、人工处理、结论）"
        "在 code/docs/ai/ai_log.md，下表是索引。",
    )
    table(
        document,
        ["#", "场景", "主要产出", "模型出的问题"],
        [
            ["1", "方案生成与判据校验", "执行方案 318 行、S0 到 S9 阶段表", "工期算成 7.2 天超过剩余 6 天；并发判据缺线程数"],
            ["2", "数据库与领域层生成", "12 表 DDL、连接与事务封装、领域 11 文件", "BEGIN IMMEDIATE 在默认 isolation_level 下必抛错；字段名不一致"],
            ["3", "状态机用例设计", "8 条允许边加 5 条禁止边用例", "把唯一 (source,event) 数写成 7（实为 8）；错误消息断言写错"],
            ["4", "并发与幂等模拟测试", "200 线程探针、幂等 4 用例", "autocommit 连接上又写 COMMIT；输出含用时无法逐字节比对"],
            ["5", "代码风格检查", "pylintrc、10.00 分", "改长行时改出括号未闭合；docstring 里写了被判据 grep 命中的字面量"],
            ["6", "坏味道（disable）压缩", "20 降到 14 条，分类达标", "第一反应是放宽 pylintrc 阈值（被红线禁止）"],
            ["7", "界面截图缺陷定位", "PrintWindow 整窗抓屏加自检", "连续 5 轮误判（先怪列宽、再怪布局顺序），真因是 DPI 与屏幕坐标"],
            ["8", "报表退房营收缺陷", "拆两套状态集合加 3 条用例", "认为退房不该算营收，与退房不释放占用矛盾"],
        ],
        widths=[0.9, 4.0, 6.4, 7.0],
    )
    caption(document, "表 3-1　大模型交互索引（完整记录见 code/docs/ai/ai_log.md）")

    document.add_paragraph("3.3　边界：哪些事不让大模型做", style="Heading 2")
    bullet(document, "判据的最终裁定：阶段是否通过由评审人独立复跑决定，执行者不能自评。")
    bullet(document, "数据的最终核对：报告里每个数字都要求一条命令原样复现，终验抽查 3 个现场跑。")
    bullet(document, "设计的取舍：改期先占新后放旧的顺序、部分唯一索引的边界，由本人按 exp1、exp2 决定，模型只负责实现与指出风险。")
    bullet(document, "合规与提交：cslab-cms 的提交、身份信息、最终 zip 的内容，均本人确认。")
    para(
        document,
        "另外说明一点：课程在 2026-11-25 发布通知，明确实验三报告允许使用大模型辅助撰写，"
        "与手册原文的报告书写禁止用大模型不同。本报告按新通知执行，但结论、案例取舍与经验总结"
        "仍由本人撰写与定稿，AI 主要用于整理表格、核对数字与润色语句；通知原文存在"
        "code/docs/report_materials/requirement_update.md。",
    )


def chapter_4(document):
    document.add_paragraph("4　让大模型做了什么", style="Heading 1")

    document.add_paragraph("4.1　功能代码生成", style="Heading 2")
    para(
        document,
        "占比最大的一块是把设计写成能跑的代码：12 表 DDL 与部分唯一索引、连接与事务封装、"
        "三个仓储接口的 SQLite 实现、状态机表驱动结构、整数分计价、履约扫描（超时取消、自动入住、"
        "未入住）、报表与对账、十屏界面。生成方式不是一次给一大段，而是按阶段分片："
        "每个阶段先给判据与字段约束，再产出文件，本人逐文件读一遍再运行。",
    )
    para(
        document,
        "有一个细节值得记录：界面表格控件是 ttk.Treeview，模型最初按每个按钮一个回调、"
        "回调里直接写 SQL 的方式生成，被本人否掉：界面层不允许出现 SQL，也不允许绕过应用服务。"
        "改成界面只调应用服务、服务再调仓储后，界面内 SQL 命中 0 的判据自然成立。",
    )

    document.add_paragraph("4.2　单元测试与模拟用户测试", style="Heading 2")
    para(
        document,
        "测试分三类。第一类是领域规则测试：13 条状态机边、计价、库存三态（0 间、恰好等于余量、"
        "超出余量）。第二类是并发与幂等：用 threading.Barrier 让 200 个线程同时抢 1 间房，"
        "断言成功 1、失败 199、锁错误 0、负库存 0、订单 1 张、逐晚快照 1 条，且禁止重试。"
        "第三类是模拟用户：ui_chain.py 起真窗口、按文字找按钮、真的调用按钮，"
        "走完登录、搜索、下单、取消被拒、店长确认、入住、退房、报表营收八步。",
    )
    code_block(
        document,
        """$ python code/tools/ui_chain.py
step 1  顾客登录         ok
step 2  搜索酒店         ok   hotels=2
step 3  提交订单         ok   booking=BK20261126...
step 4  我的订单详情     ok   status=待确认
step 5  顾客取消被拒     ok   error=PERMISSION_DENIED
step 6  店长确认         ok   status=已确认
step 7  办理入住         ok   status=已入住
step 8  办理退房         ok   status=已退房  revenue=69800
chain_steps=8  check=passed""",
    )
    caption(document, "图 4-1　界面链路八步（证据 S6_10_ui_chain.txt）")

    document.add_paragraph("4.3　风格检查与坏味道消除", style="Heading 2")
    para(
        document,
        "风格按手册点名的 pylint 加 Google 风格执行：行长 100、命名规则放开中文方法名"
        "（用例名即命题）、C0413（import 位置）因为工具与测试要先把 code/ 注入 sys.path 而带理由豁免。"
        "最终 10.00 分、0 条消息。坏味道方面，行内 disable 从 20 条压到 14 条，"
        "且分类达标（实例属性 8、参数 6、其余 0），做法是真改进而不是放宽阈值："
        "给 19 个按钮回调补 docstring、把基础设施导入提到模块顶层、给 Clock 补 source()、"
        "给账号服务抽 check_available() 并补 5 条用例。",
    )

    document.add_paragraph("4.4　文档与证据整理", style="Heading 2")
    para(
        document,
        "每个阶段的证据都落成 code/docs/evidence/ 下的文本文件，命名带阶段号与判据号，"
        "内容是可复跑命令的原样输出（含 exit code），总计 92 份。好处是报告里的每个数字都能"
        "指到一份文件、一条命令；代价是文件多，所以另外维护了 R1 到 R6 与章节、素材的对照表（附录 B）。",
    )


def chapter_5(document):
    document.add_paragraph("5　不符合预期时怎么做", style="Heading 1")
    para(
        document,
        "手册把这一条单列为报告必含项，说明老师关心的不是 AI 一次写对，而是 AI 写错时有没有发现、"
        "怎么定位、怎么修、怎么防复发。下面四个案例都真实发生过，按现象、定位、处置、防复发来写。",
    )

    document.add_paragraph("5.1　案例一：事务与并发", style="Heading 2")
    para(
        document,
        "现象：下单事务在单线程测试里全绿，但探针一跑就出现数据库被锁和同一间房卖出两张单。"
        "定位：Python 的 sqlite3 默认 isolation_level 为空串，会隐式开启事务，代码里再执行 "
        "BEGIN IMMEDIATE 就变成嵌套事务；同时多线程共用一个连接，线程检查打开后直接抛异常。"
        "处置：连接工厂固定 isolation_level 为 None（纯手动事务）、每线程独立连接、busy_timeout 5 秒、"
        "事务封装成 immediate_transaction() 并在嵌套调用时立刻抛错。"
        "防复发：把 200 线程、禁重试、四个计数写成一条命令的判据，任何人改事务都要重跑。",
    )

    document.add_paragraph("5.2　案例二：状态机边数口径", style="Heading 2")
    para(
        document,
        "现象：模型写的断言是唯一 (source,event) 有 7 个，实测失败，实际是 8 个。"
        "定位：实验一写 7 条允许转换，但按触发者拆开是 8 条（酒店确认与系统自动入住都到已入住，"
        "酒店拒单与系统超时都到已取消），所以 8 条事件、8 个唯一 (source,event)、只有 6 个唯一 "
        "(source,target)。处置：把三条口径分别断言，并在报告与追溯表里写清楚。"
        "防复发：状态机用表驱动，任何链式状态比较都会被 check_source_rules.py 的 status_compare 规则拦下。",
    )

    document.add_paragraph("5.3　案例三：截图只拍到窗口左边三分之二", style="Heading 2")
    para(
        document,
        "现象：界面本身六列都在窗内（评审人在 1640、1180、1024 三种宽度量过），但截图里合计与状态"
        "被切掉。定位过程很曲折：先后怀疑列宽、怀疑布局顺序、怀疑表格拉伸，改了五轮都不对；"
        "真正的根因是进程不是 DPI 感知（本机 150% 缩放），而抓屏用的是屏幕坐标加系统截屏接口，"
        "算出来的矩形只有真实窗口的一部分。处置：进程启动即调用 SetProcessDpiAwareness(2)，"
        "改用 PrintWindow 抓整窗，抓完自检图片宽高是否等于窗口矩形且末列右界在图中，"
        "不满足就非 0 退出；截图先落临时目录复验，通过后才覆盖仓库。"
        "防复发：把同一张图 sha256 不变就等于改动没生效写进经验，并让工具自己断言。",
    )

    document.add_paragraph("5.4　案例四：退房后营收归零", style="Heading 2")
    para(
        document,
        "现象：订单退房后，报表里那两天的营收整行消失，对账还报出每单差额 2，告警行只有裸的减号。"
        "定位：report_repository.py 里一个 ACTIVE_VALUES 被营收、入住率、对账右侧三处共用，"
        "而它不含已退房。处置：拆成 REVENUE_STATUSES（含已退房）与 OCCUPYING_VALUES（同集合但语义独立），"
        "无关联订单时告警写 NONE（无有效订单，库存多占），并补 3 条用例钉住。"
        "防复发：演示脚本必须覆盖已退房后的平账，否则这个缺陷还会躲过演示。",
    )


def chapter_6(document):
    document.add_paragraph("6　编译与运行结果", style="Heading 1")

    document.add_paragraph("6.1　编译与建库", style="Heading 2")
    para(
        document,
        "Python 没有独立编译步骤，因此用两条命令代替：compileall 证明全部模块可编译，"
        "init_db.py 证明 12 表可一键重建。两条命令都在交付包里可原样复跑。",
    )
    code_block(
        document,
        """$ python -m compileall -q code
（无输出，exit=0）

$ python code/tools/init_db.py --db code/data/app.db --seed
tables=12
foreign_keys=1
foreign_key_check=[]
integrity_check=ok
journal_mode=wal
user_version=1
rows=hotel=3 room_type=8 room_inventory=720 room_price=720 user_account=5 holiday_calendar=3
check=passed""",
    )
    caption(document, "图 6-1　编译与建库输出（证据 S1_01、S7_02）")

    document.add_paragraph("6.2　核心判据的实测输出", style="Heading 2")
    table(
        document,
        ["#", "判据", "实测关键输出", "结论"],
        [
            ["1", "三条链路端到端", "下单到退房、改期、顾客取消，9 条用例全绿", "通过"],
            ["2", "200 线程不超卖", "success=1 fail=199 locked_errors=0 negative_stock=0", "通过"],
            ["3", "幂等", "同键两次提交得到 booking 行数 1、同一订单号", "通过"],
            ["4", "改期失败整单回滚", "新日期占用回 0、旧日期不变、订单日期不变", "通过"],
            ["5", "越权与不泄露存在性", "不存在与无权返回同一错误码与同一文案", "通过"],
            ["6", "改期加锁边界声明", "交付说明与数据设计第 7 节逐字对照", "通过"],
            ["7", "超时扫描不真等", "假时钟；总耗时 204 毫秒；真实 sleep 命中 0", "通过"],
            ["8", "重复扫描不重复回补", "第二次扫描 total=0，审计不新增", "通过"],
            ["9", "审计只追加含失败", "四条业务动作加 REJECTED:CANCEL；删审计 0 命中", "通过"],
            ["10", "后台线程不炸库", "scan_once.py exit=0，无线程检查报错", "通过"],
        ],
        widths=[0.8, 4.6, 9.6, 2.0],
    )
    caption(document, "表 6-1　核心判据实测（每行对应 code/docs/evidence/ 下的一份或多份文件）")

    document.add_paragraph("6.3　界面运行结果", style="Heading 2")
    para(
        document,
        "十屏全部可进入，冒烟脚本逐屏执行构造、显示、销毁不抛异常（ui_smoke.py 10 屏全过）。"
        "下面四张图来自真实运行：登录页、顾客视角、店家视角、报表。"
        "完整 10 张在 code/docs/screenshots/，索引见同目录 INDEX.md。",
    )
    picture(document, SHOTS / "01_login.png", 15.0, "图 6-2　登录注册（两页签，登录后显示当前身份）")
    picture(document, SHOTS / "04_my_orders.png", 15.0, "图 6-3　我的订单（选中一行后上方显示详情；六种状态都有数据）")
    picture(document, SHOTS / "05_hotel_console.png", 15.0, "图 6-4　酒店订单台（五个动作按钮与状态计数）")
    picture(document, SHOTS / "10_reports.png", 15.0, "图 6-5　经营报表（入住率、营收、订单状态三页签）")


def chapter_7(document):
    document.add_paragraph("7　Git 本地仓库与远程托管", style="Heading 1")

    document.add_paragraph("7.1　分支与合并策略", style="Heading 2")
    para(
        document,
        "仓库与实验一、实验二共用同一个 GitHub 仓库，实验三代码放在 exp3/ 目录下，"
        "因此没有另起一个独立仓库；这一点与方案初稿不同，偏差登记里写了理由："
        "避免两套远端、两份 README 分裂。",
    )
    para(
        document,
        "分支策略是前六阶段直接在 main 提交，从 S7 整改起启用 feature 分支加 --no-ff 合并。"
        "这样做是因为评审人在 S7 第 1 轮指出：要求可展示 feature 分支与合并记录，而全仓只有"
        "实验二那一次合并。承认历史、从当轮起改，比事后补造假历史更诚实。"
        "当前分支：main、feature/s7r2、feature/s8、feature/s9。",
    )
    code_block(
        document,
        """$ git log --oneline --graph --all --max-count=7
*   ff7ebb7 [S8] 合并 feature/s8：Git 与远程证据
|\\
| * c855ae4 [S8] Git 与远程：8 个 gate 标签 + 分支合并记录 + 仓库卫生
* |   3e8e202 [S7] 合并 feature/s7r2：disable 从 20 降到 14
|\\ \\
| * 2179bfc [S7]整改：disable 20 降到 14（8/6/0）+ 152 用例
|/
* ac83685 [S7] 质量门禁：152 用例 / 覆盖率 92% / app 有效行 5054""",
    )
    caption(document, "图 7-1　提交图（证据 S8_02_graph.txt）")

    document.add_paragraph("7.2　标签与提交节奏", style="Heading 2")
    para(
        document,
        "每个阶段在评审通过后打一个 gate 标签，共 8 个：gate-S0 到 gate-S7，"
        "分别对应立项与工具链、数据底座、领域层、仓储与应用服务、履约调度、报表与对账、界面、"
        "质量门禁。提交信息统一带阶段前缀（S0 到 S9，以及整改），"
        "并按约定区分 AI 生成后本人审阅、AI 与本人共同、本人手写三种情况。",
    )
    table(
        document,
        ["标签", "指向", "含义"],
        [
            ["gate-S0", "40821ee 到 da2cf8f", "立项、目录、工具链、远程连通"],
            ["gate-S1", "f87ab42", "12 表 DDL、迁移、种子、事务封装"],
            ["gate-S2", "935a818", "领域层 13 类型加状态机 8 条允许边、5 条禁止边"],
            ["gate-S3", "4e332ce", "仓储实现加 200 线程不超卖"],
            ["gate-S4", "a28638e", "履约扫描（假时钟）"],
            ["gate-S5", "1f7c67e", "报表、对账、配置覆盖"],
            ["gate-S6", "2cb1c08", "十屏界面加整窗截图与界面链路"],
            ["gate-S7", "3e8e202", "质量门禁（覆盖率 92%、disable 14）"],
        ],
        widths=[2.4, 4.0, 9.0],
    )
    caption(document, "表 7-1　八阶段标签")

    document.add_paragraph("7.3　远程仓库", style="Heading 2")
    para(
        document,
        "远程托管在 GitHub：git@github.com:ChenYiFanAccount/softeng-lab1-requirements.git，"
        "主分支 main。每个阶段完成后推送 main，标签单独推送。"
        "远程可访问性用 git ls-remote 验证，输出与提交数见证据 S8_03_remote.txt。",
    )


def chapter_8(document):
    document.add_paragraph("8　质量自查与遗留问题", style="Heading 1")
    table(
        document,
        ["自查项", "结果", "依据"],
        [
            ["并发不超卖", "0 次超卖（200 线程单命令）", "S3_02_concurrency.txt"],
            ["同幂等键只出一单", "是；同顾客同酒店同时段同房型仅一条有效单", "幂等 4 条用例加部分唯一索引"],
            ["非法转换 409 且状态不变写审计", "是（13 条边用例加失败审计）", "test_state_machine、test_audit"],
            ["越权 403 不泄露存在性", "是（同一错误码、同一文案）", "test_permission 7 条"],
            ["改期失败整单回滚", "是（含写到一半失败的注入）", "test_reschedule_rollback 4 条"],
            ["释放不重复", "是（重复扫描 total=0）", "test_timeout_scan"],
            ["缺价、改价、减房低于占用", "分别拒绝：422、历史单不受影响、422", "test_pricing、test_inventory_admin"],
            ["无裸异常捕获、无浮点金额、无 SELECT 拼 SQL", "三条 grep 均 0 命中", "check_source_rules.py"],
        ],
        widths=[6.4, 6.0, 5.0],
    )
    caption(document, "表 8-1　质量自查八项")
    para(
        document,
        "遗留问题三条，如实记录：一是超长函数 3 个（place_booking 69 行、reschedule_booking 62 行、"
        "apply_theme 111 行），已登记在证据里但未拆分，因为拆分要动已通过的判据，收益低于风险；"
        "二是对账与报表的区间默认取今天起 90 天，桌面应用没有常驻调度器，靠外部计划任务触发，"
        "这一点写进了交付说明的风险段；三是界面没有键盘快捷键，只支持鼠标操作。",
    )


def chapter_9(document):
    document.add_paragraph("9　结论与体会", style="Heading 1")
    para(
        document,
        "这次实验最大的收获不是写出了 5000 行代码，而是建立了让 AI 干活、但由人来担保的流程。"
        "具体有三点体会。",
    )
    para(
        document,
        "第一，判据要能一条命令复现，否则完成只是说法。整个过程里被推翻的已完结论至少有六次，"
        "每一次都是因为评审人换了环境、换了命令重跑，数字对不上。反过来，凡是写成一条命令加固定输出的判据，"
        "返工成本都极低。",
    )
    para(
        document,
        "第二，AI 最擅长把明确的规则铺开，最不擅长发现自己理解错了。上面四个案例里，模型的错误都很自信："
        "事务写法、边数口径、截图根因、营收口径。人的价值在于提出可证伪的问题，比如这 7 个还是 8 个、"
        "为什么图里少了两列、退房到底释放没释放占用，然后让证据回答。",
    )
    para(
        document,
        "第三，工程纪律比技巧重要。禁止整目录暂存、禁止用真实 sleep 充当超时测试、禁止用 disable 掩盖错误、"
        "禁止改 pylintrc 放宽阈值，这些红线在过程中多次挡下了看起来更省事的做法，"
        "也直接决定了交付物能不能被别人复跑。",
    )


def appendix(document):
    document.add_paragraph("附录 A　复跑命令清单", style="Heading 1")
    para(document, "以下命令在 exp3/ 目录下执行（或交付包 code/ 的上一级），Python 3.12 加标准库即可。", indent=False)
    code_block(
        document,
        """python -m compileall -q code
python code/tools/init_db.py --db code/data/app.db --seed
python -m unittest discover -s code/tests -t code
python -m pylint code/app --rcfile=code/.pylintrc
coverage run --branch -m unittest discover -s code/tests -t code
coverage report -m
python code/tools/count_loc.py --root code/app
python code/tools/check_uml_sync.py --puml ../exp2/UML/UML类图.puml --app code/app
python code/tools/check_source_rules.py
python code/tools/concurrency_probe.py --threads 200 --rooms 1
python code/tools/ui_smoke.py
python code/tools/ui_chain.py
python code/tools/scan_once.py
python code/tools/reconcile_report.py --demo
python run.py""",
    )

    document.add_paragraph("附录 B　R1–R6 与本书章节对照", style="Heading 1")
    table(
        document,
        ["报告要求", "章节", "素材文件"],
        [
            ["R1 UML 到代码的方法、源码规模", "第 1、2 章", "code/docs/uml_map.md、loc.csv、evidence/S7_05"],
            ["R2 大模型如何参与", "第 3 章", "code/docs/ai/ai_log.md、evidence/S6_06_pylint.txt"],
            ["R3 让大模型做了什么", "第 4 章", "ai_log.md（8 条）、evidence/S6_10_ui_chain.txt"],
            ["R4 不符合预期时怎么做", "第 5 章", "交付说明的整改段、evidence/S5_10、S6_11"],
            ["R5 编译运行结果", "第 6 章", "evidence/S1_01、S3_02、S4_01、S6_01、S7_02、screenshots/"],
            ["R6 Git 与远程", "第 7 章", "evidence/S8_01_tags.txt、S8_02_graph.txt、S8_03_remote.txt"],
        ],
        widths=[6.4, 2.6, 8.4],
    )
    caption(document, "表 B-1　六项要求与章节、素材的对应")

    document.add_paragraph("附录 C　参考文献", style="Heading 1")
    for item in [
        "[1] 实验三：软件实现与构建. 软件工程实践课程手册, 2026.",
        "[2] 实验一 需求规格与项目参数（exp1/requirements.md、exp1/项目参数.md）, 2026.",
        "[3] 实验二 设计基线：模块划分与交互、数据设计（exp2/设计基线/）, 2026.",
        "[4] 实验二 UML 类图 v1.1（exp2/UML/UML类图.puml）, 2026.",
        "[5] Python Software Foundation. sqlite3 — DB-API 2.0 interface for SQLite databases. Python 3.12 Documentation.",
        "[6] SQLite Consortium. SQLite Documentation: Transactions, WAL mode, Partial Indexes.",
        "[7] Pylint contributors. Pylint User Manual and Messages Reference.",
        "[8] Python Software Foundation. tkinter — Python interface to Tcl/Tk; ttk themes.",
        "[9] Microsoft. PrintWindow function (winuser.h); SetProcessDpiAwareness (shcore.h). Windows API Reference.",
        "[10] Coverage.py documentation. Branch coverage measurement.",
    ]:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        set_font(paragraph.add_run(item), size=9.5)


def add_header_footer(document):
    section = document.sections[0]
    header = section.header.paragraphs[0]
    header.text = ""
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(header.add_run("酒店预订管理系统 · 实验三 软件实现与构建"), size=9)
    header.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(footer.add_run(STUDENT_NAME + "　" + STUDENT_ID), size=9)
    footer.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def main():
    document = Document()
    style_document(document)
    build_cover(document)
    build_toc(document)
    chapter_1(document)
    chapter_2(document)
    chapter_3(document)
    chapter_4(document)
    chapter_5(document)
    chapter_6(document)
    chapter_7(document)
    chapter_8(document)
    chapter_9(document)
    appendix(document)
    add_header_footer(document)

    target = STAGE / "实验报告.docx"
    document.save(target)
    print("saved:", target)
    print("paragraphs=", len(document.paragraphs), "tables=", len(document.tables))


if __name__ == "__main__":
    main()
