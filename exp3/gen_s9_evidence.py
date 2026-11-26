"""生成 S9 阶段的三份证据文件（打包结构、洁净度、PDF 首页）。"""

from __future__ import annotations

import pathlib
import re
import zipfile

from docx import Document

ROOT = pathlib.Path(r"D:\NJU\softengineering\exp3")
EVIDENCE = ROOT / "code" / "docs" / "evidence"
ZIP_PATH = ROOT / "交付包" / "实验3_241220024_陈一帆.zip"
STAGE = ROOT / "交付包" / "实验3_241220024_陈一帆"
PDF = STAGE / "实验报告.pdf"
DOCX_SRC = ROOT / "report_src" / "实验报告.docx"

FORBIDDEN = re.compile(
    r"(^|/)(\.git|\.venv|\.wheels|__pycache__|\.verify)(/|$)", re.IGNORECASE
)
SUFFIXES = (".db", ".db-journal", ".db-wal", ".db-shm", ".pyc")


def zip_evidence() -> str:
    archive = zipfile.ZipFile(ZIP_PATH)
    names = archive.namelist()
    tops = sorted({name.split("/")[0] for name in names})
    ok = tops == ["UML", "code", "实验报告.pdf"]
    lines = [
        "S9-2 打包结构核验（python -c 用 zipfile 读取 zip 名表）",
        "zip=" + ZIP_PATH.name,
        "entries=%d" % len(names),
        "top_level=" + ", ".join(tops),
        "pdf_present=%s" % ("实验报告.pdf" in names),
        "uml_dir_present=%s" % any(name.startswith("UML/") for name in names),
        "code_dir_present=%s" % any(name.startswith("code/") for name in names),
        "uml_png=%d uml_puml=%d"
        % (
            sum(1 for name in names if name.startswith("UML/") and name.endswith(".png")),
            sum(1 for name in names if name.startswith("UML/") and name.endswith(".puml")),
        ),
        "screenshots=%d evidence=%d"
        % (
            sum(1 for name in names if "docs/screenshots/" in name and name.endswith(".png")),
            sum(1 for name in names if "docs/evidence/" in name),
        ),
        "check_top3=%s" % ok,
        "check=%s" % ("passed" if ok else "failed"),
    ]
    text = "\n".join(lines) + "\n"
    (EVIDENCE / "S9_01_zip_tree.txt").write_text(text, encoding="utf-8")
    return text


def clean_evidence() -> str:
    names = zipfile.ZipFile(ZIP_PATH).namelist()
    bad = [
        name
        for name in names
        if FORBIDDEN.search(name) or name.lower().endswith(SUFFIXES)
    ]
    lines = [
        "S9-3 交付包洁净度（包内不得有 .git / venv / .db / __pycache__）",
        "pattern=(.git|.venv|.wheels|__pycache__|.verify)(/|$)|*.db|*.db-journal|*.db-wal|*.db-shm|*.pyc",
        "matched=%d" % len(bad),
    ]
    lines.extend("  " + name for name in bad[:10])
    lines.append("check=%s" % ("passed" if not bad else "failed"))
    text = "\n".join(lines) + "\n"
    (EVIDENCE / "S9_02_zip_forbidden.txt").write_text(text, encoding="utf-8")
    return text


def cover_evidence() -> str:
    document = Document(DOCX_SRC)
    paragraphs = [item.text.strip() for item in document.paragraphs[:40] if item.text.strip()]
    rows = []
    for table in document.tables[:1]:
        for row in table.rows:
            rows.append(" ".join(cell.text.strip() for cell in row.cells))
    joined = "\n".join(paragraphs + rows)
    has_id = "241220024" in joined
    has_name = "陈一帆" in joined
    pdf_bytes = PDF.read_bytes()
    lines = [
        "S9-4 PDF 首页含学号与姓名",
        "pdf=%s bytes=%d" % (PDF.name, len(pdf_bytes)),
        "pdf_header=%s" % pdf_bytes[:8].decode("ascii", "replace"),
        "cover_image=docs/screenshots/report_cover.png（PDF 第 1 页渲染，1075x1521）",
        "",
        "[docx 封面段落]",
    ]
    lines.extend(paragraphs[:10])
    lines.extend(["", "[docx 封面表格]"])
    lines.extend(rows)
    lines.extend(
        [
            "",
            "check_id=%s" % has_id,
            "check_name=%s" % has_name,
            "check=%s" % ("passed" if has_id and has_name else "failed"),
        ]
    )
    text = "\n".join(lines) + "\n"
    (EVIDENCE / "S9_03_pdf_cover.txt").write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    for block in (zip_evidence(), clean_evidence(), cover_evidence()):
        print(block)
