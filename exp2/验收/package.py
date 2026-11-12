"""S9 打包：把交付物组装成「实验2_241220024_陈一帆/」目录并打成同名 zip。

白名单（只有这三样进包）：
  实验报告.pdf
  UML/      8 组 .puml + .png（同名成对）
  UI界面/   界面01.png … 界面17.png
刻意排除：UI界面/_src/（gen.py、style.css、17 份 HTML、shot.py）、实验报告_预览.*、
        验收/ 下的一切（check.py、评审报告、req_index.json、_pdfimg/）。

用法：python exp2/验收/package.py [--check-only]
"""
import shutil
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

EXP2 = Path(r"D:\NJU\softengineering\exp2")
NAME = "实验2_241220024_陈一帆"
OUT_DIR = EXP2 / "交付"
PKG = OUT_DIR / NAME
ZIP = OUT_DIR / f"{NAME}.zip"
PDF = EXP2 / "实验报告.pdf"
UML = EXP2 / "UML"
UI = EXP2 / "UI界面"
UI_COUNT = 17


def collect() -> list[tuple[Path, str]]:
    """返回 [(源文件, zip 内相对路径)]，顺序稳定，便于逐项核对。"""
    items: list[tuple[Path, str]] = []
    if not PDF.exists():
        raise SystemExit(f"缺 {PDF.name}：先跑 python exp2\\验收\\build_report_pdf.py 实验报告.pdf")
    items.append((PDF, f"{NAME}/实验报告.pdf"))

    pumls = sorted(UML.glob("*.puml"))
    if not pumls:
        raise SystemExit("UML 目录下没有 .puml")
    for p in pumls:
        png = p.with_suffix(".png")
        if not png.exists():
            raise SystemExit(f"{p.name} 没有对应的 .png（先重渲）")
        items.append((p, f"{NAME}/UML/{p.name}"))
        items.append((png, f"{NAME}/UML/{png.name}"))

    for i in range(1, UI_COUNT + 1):
        png = UI / f"界面{i:02d}.png"
        if not png.exists():
            raise SystemExit(f"缺 {png.name}")
        items.append((png, f"{NAME}/UI界面/{png.name}"))
    return items


def build(items: list[tuple[Path, str]]) -> None:
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)
    (PKG / "UML").mkdir()
    (PKG / "UI界面").mkdir()
    for src, rel in items:
        dst = OUT_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for _, rel in items:
            z.write(OUT_DIR / rel, rel)


def verify(items: list[tuple[Path, str]]) -> int:
    bad = 0
    with zipfile.ZipFile(ZIP) as z:
        names = z.namelist()
        expect = {rel for _, rel in items}
        extra = sorted(set(names) - expect)
        missing = sorted(expect - set(names))
        if extra or missing:
            bad += 1
            print(f"[FAIL] zip 内容与白名单不一致：多 {extra[:3]} 少 {missing[:3]}")
        if any("/_src/" in n for n in names):
            bad += 1
            print("[FAIL] zip 里出现 _src/（源码不该交付）")
        if any(n.endswith((".md", ".html")) or "预览" in n or "_pdfimg" in n for n in names):
            bad += 1
            print("[FAIL] zip 里出现 .md/.html/预览件/_pdfimg")
    mb = ZIP.stat().st_size / 1048576
    if mb > 20:
        bad += 1
        print(f"[FAIL] zip {mb:.2f} MB 超过 20 MB")
    n_puml = sum(1 for n in names if n.endswith(".puml")) if "names" in dir() else 0
    print(f"[ok] {ZIP.name}: {len(names)} 个文件（puml {n_puml} / png {len(names) - 3} / pdf 1），"
          f"{mb:.2f} MB，目录 {PKG}")
    return bad


if __name__ == "__main__":
    items = collect()
    if "--check-only" not in sys.argv:
        build(items)
    sys.exit(1 if verify(items) else 0)
