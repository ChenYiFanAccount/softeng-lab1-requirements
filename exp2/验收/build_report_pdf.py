"""Markdown → A4 HTML → Edge 无头打印 PDF（报告预览与最终 PDF 共用）。

只支持本报告实际用到的语法：ATX 标题、表格、图片、加粗、行内代码、引用、无序列表、
水平线、以及两段原样透传的 <div class="cover"> / <div class="toc"> 块。
"""
import html
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"D:\NJU\softengineering\exp2")
SRC = ROOT / "实验报告.md"
HTML_OUT = ROOT / "实验报告_预览.html"
PDF_OUT = ROOT / "实验报告_预览.pdf"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PROFILE = Path(r"D:\softeng-env\_edge_profile_pdf")
IMG_CACHE = ROOT / "验收" / "_pdfimg"   # 压缩后的图，被 exp2/验收/_* 忽略，不入库


def shrink(src: str) -> str:
    """报告里引用的是 2x 原图（UI 2880×1800、UML 最大 2748 宽）。
    直接嵌进 PDF 会让体积到 20MB+，这里按用途生成压缩版：
    UML 保留 2000px 宽的 PNG（文字要清楚），UI 截图降到 1600px 宽的 JPEG q88。
    返回相对 实验报告_预览.html 的路径。"""
    from PIL import Image

    p = SRC.parent / src
    if not p.exists():
        print("WARN 图片不存在:", src)
        return src
    IMG_CACHE.mkdir(parents=True, exist_ok=True)
    is_uml = "UML" in src
    max_w = 2000 if is_uml else 1600
    out = IMG_CACHE / (p.stem + ("_uml.png" if is_uml else "_ui.jpg"))
    im = Image.open(p).convert("RGB" if not is_uml else "RGBA")
    if im.width > max_w:
        h = round(im.height * max_w / im.width)
        im = im.resize((max_w, h), Image.LANCZOS)
    if is_uml:
        im.save(out, format="PNG", optimize=True)
    else:
        im.convert("RGB").save(out, format="JPEG", quality=88, optimize=True)
    return str(out.relative_to(SRC.parent)).replace("\\", "/")


CSS = """
@page { size: A4; margin: 20mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "微软雅黑", "SimSun", serif;
  font-size: 10.5pt; line-height: 1.72; color: #1a1a1a; margin: 0;
  padding: 0;
}
.rh, .rf {
  position: fixed; left: 0; right: 0; font-size: 8.5pt; color: #666;
  letter-spacing: .2px;
}
.rh { top: -16mm; padding: 0 0 2mm; border-bottom: .5pt solid #d0d7de; background: #fff; }
.rf { bottom: -16mm; padding: 2mm 0 0; border-top: .5pt solid #d0d7de; background: #fff;
      text-align: center; }
h1 { font-size: 16pt; margin: 0 0 8pt; }
h2 { font-size: 14pt; margin: 18pt 0 8pt; padding-bottom: 4pt; border-bottom: 1pt solid #2f6fed;
     page-break-before: always; page-break-after: auto; }
h2:first-of-type { page-break-before: auto; }
h3 { font-size: 12pt; margin: 14pt 0 6pt; page-break-after: avoid; }
h4 { font-size: 11.5pt; font-weight: 700; margin: 13pt 0 5pt; padding-left: 6pt;
     border-left: 2.5pt solid #9db4e8; page-break-after: avoid; }
p { margin: 4pt 0; text-align: left; }
ul { margin: 4pt 0 4pt 18pt; padding: 0; }
li { margin: 2pt 0; }
code { font-family: Consolas, monospace; font-size: 9.5pt; background: #f3f5f8;
       padding: 0 2px; border-radius: 2px; }
blockquote { margin: 6pt 0; padding: 4pt 8pt; border-left: 2.5pt solid #b9c4d4;
             background: #f8fafc; color: #333; font-size: 10pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9.5pt;
        page-break-inside: auto; }
th, td { border: .5pt solid #c7ced8; padding: 3pt 5pt; vertical-align: top; }
th { background: #eef2f8; font-weight: 600; }
tr { page-break-inside: avoid; }
img { max-width: 100%; max-height: 205mm; display: block; margin: 8pt auto 2pt; page-break-inside: avoid; }
hr { border: none; border-top: .5pt solid #c7ced8; margin: 10pt 0; }
.cover { height: 245mm; display: flex; flex-direction: column; justify-content: center;
         align-items: center; text-align: center; page-break-after: always; }
.cover h1 { font-size: 26pt; line-height: 1.5; margin: 10mm 0 14mm; }
.cover p { margin: 3mm 0; font-size: 11pt; }
.toc { page-break-after: always; }
.toc h2 { page-break-before: auto; margin-top: 0; }
.toc ul ul { margin-left: 16pt; }
"""

HEADER = "软件工程 · 实验二　软件设计与建模　|　酒店预订系统　|　241220024 陈一帆"


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("<div"):
            # div 块：外壳原样保留，内部仍按 Markdown 转换（封面与目录里写的是 Markdown）
            shell_open = ln
            cls = re.search(r'class="([^"]+)"', shell_open)
            cls = cls.group(1) if cls else ""
            i += 1
            inner, depth = [], 1
            while i < len(lines):
                if lines[i].strip().startswith("</div>"):
                    depth -= 1
                    if depth == 0:
                        break
                else:
                    depth += lines[i].count("<div") - lines[i].count("</div>")
                inner.append(lines[i])
                i += 1
            i += 1  # 跳过 </div>
            out.append(f'<div class="{cls}">')
            out.append(md_to_html("\n".join(inner)))
            out.append("</div>")
            continue
        if ln.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", ln)
            if m:
                alt, src = m.group(1), m.group(2)
                out.append(f'<img src="{html.escape(shrink(src))}" alt="{html.escape(alt)}">')
                i += 1
                continue
        if re.match(r"^(#{1,4})\s", ln):
            level = len(re.match(r"^#+", ln).group(0))
            text = ln[level:].strip()
            out.append(f"<h{level}>{inline(text)}</h{level}>")
            i += 1
            continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in header)
                       + "</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue
        if ln.startswith("> "):
            out.append(f"<blockquote>{inline(ln[2:])}</blockquote>")
            i += 1
            continue
        if re.match(r"^[-*]\s", ln) or re.match(r"^\s{2,}[-*]\s", ln):
            items = []
            while i < len(lines) and (re.match(r"^[-*]\s", lines[i]) or re.match(r"^\s{2,}[-*]\s", lines[i])):
                raw = lines[i].lstrip()[2:]
                indent = len(lines[i]) - len(lines[i].lstrip())
                items.append((indent, raw))
                i += 1
            out.append("<ul>")
            for indent, raw in items:
                cls = ' style="margin-left:14pt"' if indent >= 2 else ""
                out.append(f"<li{cls}>{inline(raw)}</li>")
            out.append("</ul>")
            continue
        if ln.strip() == "---":
            out.append("<hr>")
            i += 1
            continue
        if ln.strip() == "":
            i += 1
            continue
        out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


md = SRC.read_text(encoding="utf-8")
body = md_to_html(md)
page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>酒店预订系统的软件设计与建模</title>
<style>{CSS}</style></head>
<body>
{body}
</body></html>"""

HTML_OUT.write_text(page, encoding="utf-8", newline="\n")
print("html", len(page))

args = [EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        f"--user-data-dir={PROFILE}", f"--print-to-pdf={PDF_OUT}",
        HTML_OUT.resolve().as_uri()]
r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("rc", r.returncode, "pdf", PDF_OUT.stat().st_size if PDF_OUT.exists() else 0)
if r.stderr.strip():
    print("err", r.stderr.strip()[:200])


def stamp_header_footer(pdf: Path) -> None:
    """页眉 / 页脚 / 页码：先生成纯文字透明图章，再用 pypdf 逐页 merge。

    为什么不在 PyMuPDF 里直接改原文档再 save：那样会把图片流重新编码，
    Edge 直出的 4.3MB 稿子会涨到 16–23MB（实测三种 save 参数都涨）。
    merge 只往页面追加一层文字内容流，图片流原样保留。
    """
    import pymupdf
    from pypdf import PdfReader, PdfWriter

    font_file = r"C:\Windows\Fonts\msyh.ttc"
    gray = (0.42, 0.45, 0.5)

    with pymupdf.open(pdf) as src:
        n = src.page_count
        w, h = src[0].rect.width, src[0].rect.height

    stamp = pymupdf.open()
    for i in range(n):
        page = stamp.new_page(width=w, height=h)
        if i > 0:  # 封面不盖页眉
            page.insert_text((56, 34), HEADER, fontsize=8, fontname="msyh",
                             fontfile=font_file, color=gray)
            page.draw_line(pymupdf.Point(56, 40), pymupdf.Point(w - 56, 40),
                           color=(0.82, 0.85, 0.88), width=0.5)
        page.draw_line(pymupdf.Point(56, h - 40), pymupdf.Point(w - 56, h - 40),
                       color=(0.82, 0.85, 0.88), width=0.5)
        foot = f"酒店预订系统 · 软件工程实验二 · 2026-11-13　　- {i + 1} / {n} -"
        font = pymupdf.Font(fontfile=font_file)
        tw = font.text_length(foot, fontsize=8)
        page.insert_text(((w - tw) / 2, h - 28), foot, fontsize=8, fontname="msyh",
                         fontfile=font_file, color=gray)

    # 关键：msyh.ttc 整份约 19MB，不 subset 的话每页都背一份字库（实测 PDF 从 4.3MB 涨到 23MB）
    stamp.subset_fonts()
    tmp_stamp = pdf.with_name("_stamp.pdf")
    stamp.save(tmp_stamp, garbage=4, deflate=True)
    stamp.close()

    # pypdf 7 起：页面必须先挂到 writer 上才能 merge（replace_contents 的约束）
    overlay = PdfReader(str(tmp_stamp))
    writer = PdfWriter(clone_from=str(pdf))
    for idx, page in enumerate(writer.pages):
        page.merge_page(overlay.pages[idx])

    out = pdf.with_name(pdf.stem + "_tmp.pdf")
    with out.open("wb") as fh:
        writer.write(fh)
    out.replace(pdf)
    tmp_stamp.unlink(missing_ok=True)
    print("stamped", n, "pages ->", round(pdf.stat().st_size / 1048576, 2), "MB")


stamp_header_footer(PDF_OUT)
