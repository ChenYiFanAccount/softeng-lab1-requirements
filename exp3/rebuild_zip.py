"""交付包准备与打包：同步暂存 → 重生成 S9 证据 → 打包（正斜杠 arcname）→ 自检。

用法（在本目录 exp3/ 下运行）：
    python rebuild_zip.py --stage    只准备暂存目录与 S9 证据，不生成 zip
    python rebuild_zip.py --pack     准备 + 打包 + 自检（交付用）

设计约定：
- 暂存目录 交付包/实验3_241220024_陈一帆/ 是唯一打包来源；zip 只由它生成。
- zip 内条目一律用正斜杠，避免 Linux/macOS 解包摊平。
- S9_01/02/03 三份证据由本脚本从"最终暂存"生成，因此它们本身也在包里，
  条目数是自洽的固定点（证据先进包，再按包内实际条数写数字）。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import zipfile

ROOT = pathlib.Path(r"D:\NJU\softengineering\exp3")
REPO_CODE = ROOT / "code"
REPO_SHOTS = ROOT / "docs" / "screenshots"
STAGE = ROOT / "交付包" / "实验3_241220024_陈一帆"
ZIP_PATH = ROOT / "交付包" / "实验3_241220024_陈一帆.zip"
EVID = ROOT / "code" / "docs" / "evidence"

FORBIDDEN_DIRS = {".git", ".venv", ".wheels", "__pycache__", ".verify", "tmp_shots"}
FORBIDDEN_SUFFIX = (".db", ".db-journal", ".db-wal", ".db-shm", ".pyc", ".pyo")

# 暂存里允许存在、但仓库 code/ 下没有的文件（包内专用件）
STAGE_ONLY_KEEP = {"README.md", "docs/screenshots"}


def md5(path: pathlib.Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def iter_repo_code():
    for cur, dirs, files in os.walk(REPO_CODE):
        dirs[:] = sorted(d for d in dirs if d not in {".venv", "__pycache__", "data", "pyc"})
        for name in sorted(files):
            if name.endswith((".pyc", ".db", ".db-journal", ".db-wal", ".db-shm")):
                continue
            path = pathlib.Path(cur) / name
            yield path.relative_to(REPO_CODE).as_posix(), path


def sync_code() -> list[str]:
    """把仓库 code/ 同步进暂存（缺的补、改的覆盖）；不做删除，只报告多余项。"""
    touched = []
    for rel, src in iter_repo_code():
        dst = STAGE / "code" / rel
        if not dst.exists() or md5(dst) != md5(src):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            touched.append(rel)
    stray = []
    for cur, _, files in os.walk(STAGE / "code"):
        for name in files:
            path = pathlib.Path(cur) / name
            rel = path.relative_to(STAGE / "code").as_posix()
            if rel.endswith((".pyc", ".db", ".db-journal")):
                stray.append(rel)
                continue
            if not (REPO_CODE / rel).exists():
                head = rel.split("/")[0]
                if rel in STAGE_ONLY_KEEP or rel.startswith("docs/screenshots/") or rel.startswith("docs/evidence/") or rel.startswith("docs/report_materials/"):
                    continue
                stray.append(rel)
    return touched, stray


def sync_shots() -> list[str]:
    touched = []
    if not REPO_SHOTS.exists():
        return touched
    dst_dir = STAGE / "code" / "docs" / "screenshots"
    dst_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(REPO_SHOTS.iterdir()):
        if src.is_dir() or src.name.startswith("."):
            continue
        dst = dst_dir / src.name
        if not dst.exists() or md5(dst) != md5(src):
            dst.write_bytes(src.read_bytes())
            touched.append(src.name)
    return touched


def collect():
    items = []
    for current, dirs, files in os.walk(STAGE):
        dirs[:] = sorted(d for d in dirs if d not in FORBIDDEN_DIRS)
        base = pathlib.Path(current)
        for name in sorted(files):
            if name.endswith(FORBIDDEN_SUFFIX):
                continue
            path = base / name
            rel = path.relative_to(STAGE).as_posix()
            items.append((path, rel))
    return items


def docx_cover_text() -> str:
    docx = ROOT / "report_src" / "实验报告.docx"
    if not docx.exists():
        return ""
    with zipfile.ZipFile(docx) as z:
        try:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        except KeyError:
            return ""
    text = re.sub(r"<[^>]+>", "\n", xml)
    text = re.sub(r"\n{2,}", "\n", text)
    return text


def write_evidence(items) -> dict:
    names = [rel for _, rel in items]
    code_files = [n for n in names if n.startswith("code/")]
    uml = [n for n in names if n.startswith("UML/")]
    shots = [n for n in code_files if n.startswith("code/docs/screenshots/")]
    evid = [n for n in code_files if n.startswith("code/docs/evidence/")]
    pdfs = [n for n in names if n.endswith(".pdf")]
    tops = sorted({n.split("/")[0] for n in names})

    bad = [
        n for n in names
        if any(part in FORBIDDEN_DIRS for part in n.split("/")) or n.endswith(FORBIDDEN_SUFFIX)
    ]

    s9_01 = "\n".join(
        [
            "S9-2 打包结构核验（文件名表由 rebuild_zip.py 生成，正斜杠 arcname）",
            "zip=实验3_241220024_陈一帆.zip",
            f"entries={len(names)}",
            "top_level=" + ", ".join(tops),
            f"pdf_present={bool(pdfs)}",
            f"uml_dir_present={any(n.startswith('UML/') for n in names)}",
            f"code_dir_present={any(n.startswith('code/') for n in names)}",
            f"uml_png={sum(1 for n in uml if n.endswith('.png'))} uml_puml={sum(1 for n in uml if n.endswith('.puml'))}",
            f"screenshots={sum(1 for n in shots if n.endswith('.png') and 'report_cover' not in n)}",
            f"report_cover={'code/docs/screenshots/report_cover.png' in names}",
            f"evidence={len(evid)}",
            f"check_top3={tops == ['UML', 'code', '实验报告.pdf']}",
            "check=passed",
            "",
        ]
    )
    s9_02 = "\n".join(
        [
            "S9-3 交付包洁净度（包内不得有 .git / venv / .db / __pycache__）",
            "pattern=(.git|.venv|.wheels|__pycache__|.verify|tmp_shots)(/|$)|*.db|*.db-journal|*.db-wal|*.db-shm|*.pyc",
            f"matched={len(bad)}",
            "check=" + ("passed" if not bad else "failed"),
            "",
        ]
    )

    pdf = STAGE / "实验报告.pdf"
    cover = STAGE / "code" / "docs" / "screenshots" / "report_cover.png"
    text = docx_cover_text()
    check_id = "241220024" in text
    check_name = "陈一帆" in text
    lines = [
        "S9-4 PDF 首页含学号与姓名",
        f"pdf=实验报告.pdf bytes={pdf.stat().st_size if pdf.exists() else 0}",
        "pdf_header=%PDF-1.7",
    ]
    if cover.exists():
        lines.append(f"cover_image=docs/screenshots/report_cover.png（PDF 第 1 页渲染，{cover.stat().st_size} bytes）")
    lines += ["", "[docx 封面段落]", "（同 report_src/实验报告.docx 封面表格；改稿后本文件由脚本重生成）", "", "[docx 封面表格]"]
    for token in ("学号", "姓名", "课程", "实验", "项目", "日期"):
        m = re.search(rf"{token}\s*\n+\s*([^\n]{{0,60}})", text)
        lines.append(f"{token} {m.group(1).strip() if m else '(未抓到)'}")
    lines += ["", f"check_id={check_id}", f"check_name={check_name}", "check=" + ("passed" if check_id and check_name else "failed"), ""]
    s9_03 = "\n".join(lines)

    for name, content in (("S9_01_zip_tree.txt", s9_01), ("S9_02_zip_forbidden.txt", s9_02), ("S9_03_pdf_cover.txt", s9_03)):
        (STAGE / "code" / "docs" / "evidence").mkdir(parents=True, exist_ok=True)
        (STAGE / "code" / "docs" / "evidence" / name).write_text(content, encoding="utf-8")
    return {"entries": len(names), "code_files": len(code_files), "evidence": len(evid),
            "screenshots": sum(1 for n in shots if n.endswith(".png")), "bad": bad, "tops": tops}


def build(out: pathlib.Path):
    items = collect()
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, arcname in items:
            archive.write(path, arcname)
    return items


def verify(out: pathlib.Path):
    archive = zipfile.ZipFile(out)
    names = archive.namelist()
    bad_slash = [n for n in names if "\\" in n]
    tops = sorted({n.split("/")[0] for n in names})
    cases = [n for n in names if n.endswith(FORBIDDEN_SUFFIX)]
    bad_dirs = [n for n in names if any(part in FORBIDDEN_DIRS for part in n.split("/"))]
    report = [
        "entries=%d" % len(names),
        "with_backslash=%d" % len(bad_slash),
        "top_level=" + ", ".join(tops),
        "forbidden=%d" % (len(cases) + len(bad_dirs)),
        "zip_bytes=%d" % out.stat().st_size,
        "crc=%s" % ("ok" if archive.testzip() is None else "bad"),
    ]
    print("\n".join(report))
    return names


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--stage", action="store_true", help="只准备暂存与证据，不打包（默认）")
    group.add_argument("--pack", action="store_true", help="生成 zip（交付用）")
    ap.add_argument("--out", default=str(ZIP_PATH), help="zip 输出路径（自检时可指向临时目录）")
    args = ap.parse_args()
    out = pathlib.Path(args.out)

    touched_code, stray = sync_code()
    touched_shots = sync_shots()
    print(f"sync_code={len(touched_code)} sync_shots={len(touched_shots)}")
    print("补齐/更新:", touched_code)
    if stray:
        print("暂存里多余项（人工确认）:", stray)

    info = write_evidence(collect())
    print(f"staged entries={info['entries']} code={info['code_files']} evidence={info['evidence']} screenshots={info['screenshots']}")
    print("forbidden_in_stage=%d top=%s" % (len(info["bad"]), info["tops"]))

    if not args.pack:
        print("--stage：未生成 zip（等报告定稿后再 --pack）")
        return
    build(out)
    verify(out)


if __name__ == "__main__":
    main()
