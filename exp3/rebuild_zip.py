"""重打包交付 zip：正斜杠 arcname、包含 report_cover.png、逐条自检。"""

from __future__ import annotations

import os
import pathlib
import zipfile

ROOT = pathlib.Path(r"D:\NJU\softengineering\exp3")
STAGE = ROOT / "交付包" / "实验3_241220024_陈一帆"
ZIP_PATH = ROOT / "交付包" / "实验3_241220024_陈一帆.zip"

FORBIDDEN_DIRS = {".git", ".venv", ".wheels", "__pycache__", ".verify"}
FORBIDDEN_SUFFIX = (".db", ".db-journal", ".db-wal", ".db-shm", ".pyc", ".pyo")


def collect():
    items = []
    for current, dirs, files in os.walk(STAGE):
        dirs[:] = sorted(d for d in dirs if d not in FORBIDDEN_DIRS)
        base = pathlib.Path(current)
        rel_dir = base.relative_to(STAGE).as_posix()
        for name in sorted(files):
            if name.endswith(FORBIDDEN_SUFFIX):
                continue
            path = base / name
            rel = path.relative_to(STAGE).as_posix()
            items.append((path, rel))
    return items


def build():
    items = collect()
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, arcname in items:
            if arcname.endswith("/"):
                info = zipfile.ZipInfo(arcname)
                info.external_attr = 0o40755 << 16
                archive.writestr(info, b"")
            else:
                archive.write(path, arcname)
    return items


def verify():
    archive = zipfile.ZipFile(ZIP_PATH)
    names = archive.namelist()
    bad_slash = [n for n in names if "\\" in n]
    tops = sorted({n.split("/")[0] for n in names})
    cases = [n for n in names if os.path.basename(n).lower().endswith(FORBIDDEN_SUFFIX)]
    bad_dirs = [n for n in names if any(part in FORBIDDEN_DIRS for part in n.split("/"))]
    code_files = [n for n in names if n.startswith("code/") and not n.endswith("/")]
    report = [
        "entries=%d" % len(names),
        "with_backslash=%d" % len(bad_slash),
        "top_level=" + ", ".join(tops),
        "code_files=%d" % len(code_files),
        "cover_present=%s" % ("code/docs/screenshots/report_cover.png" in names),
        "forbidden_files=%d" % len(cases),
        "forbidden_dirs=%d" % len(bad_dirs),
        "zip_bytes=%d" % ZIP_PATH.stat().st_size,
    ]
    print("\n".join(report))
    for name in bad_slash[:3]:
        print("  bad:", name)
    return names, report


if __name__ == "__main__":
    build()
    _, report = verify()
