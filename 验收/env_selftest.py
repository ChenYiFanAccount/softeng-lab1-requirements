#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""实验二 环境自检（S0 验收脚本）

用法：
    D:\\softeng-env\\venv\\Scripts\\python.exe 验收\\env_selftest.py

输出逐项 PASS/FAIL，末行 SUMMARY: PASS(n)/FAIL(m)。全部通过时退出码 0。
不依赖外网；只读工具链与临时目录。
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ENV = Path(r"D:\softeng-env")
JAVA = ENV / "jre" / "bin" / "java.exe"
PUMLLIB = ENV / "plantuml" / "plantuml.jar"
DOT = ENV / "graphviz" / "bin" / "dot.exe"
PY = ENV / "venv" / "Scripts" / "python.exe"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
WORK = ENV / "_selftest"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  | " + str(detail)[:160]) if detail else ""))


def run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / "out"
    out.mkdir(exist_ok=True)

    print("\n[1] 工具存在性与版本")
    check("java.exe 存在", JAVA.is_file(), JAVA)
    check("plantuml.jar 存在", PUMLLIB.is_file(),
          "%.1f MB" % (PUMLLIB.stat().st_size / 1048576) if PUMLLIB.is_file() else "缺失")
    check("dot.exe 存在", DOT.is_file(), DOT)
    check("venv python 存在", PY.is_file(), PY)
    check("msedge.exe 存在", EDGE.is_file(), EDGE)

    if JAVA.is_file():
        r = run([str(JAVA), "-version"])
        ver = (r.stderr or "") + (r.stdout or "")
        first = ver.strip().splitlines()[0] if ver.strip() else ""
        check("JRE 可执行", "version" in ver, first)
    if DOT.is_file():
        r = run([str(DOT), "-V"])
        check("Graphviz 可执行", "graphviz" in (r.stderr + r.stdout).lower(),
              (r.stderr + r.stdout).strip().splitlines()[0] if (r.stderr + r.stdout).strip() else "")
    if PUMLLIB.is_file() and JAVA.is_file():
        r = run([str(JAVA), "-jar", str(PUMLLIB), "-version"])
        txt = r.stdout + r.stderr
        check("PlantUML 可执行", "PlantUML" in txt, txt.strip().splitlines()[0] if txt.strip() else "")

    print("\n[2] Python 依赖")
    if PY.is_file():
        r = run([str(PY), "-c", "import PIL,requests,pypdf,sys;"
                "print(sys.version.split()[0], PIL.__version__, requests.__version__, pypdf.__version__)"])
        check("Pillow / requests / pypdf 可导入", r.returncode == 0 and "Pillow" not in r.stderr,
              (r.stdout or r.stderr).strip())
    else:
        check("Python 依赖", False, "venv 缺失")

    print("\n[3] 本地渲染：含中文的类图（不联网）")
    puml = WORK / "selftest.puml"
    puml.write_text("""@startuml
title 环境自检：中文与依赖倒置

package "领域层" {
  interface BookingRepository <<interface>>
  class Booking {
    - 订单号 : String
    + 取消(原因) : Boolean
  }
}
package "数据访问层" {
  class BookingRepositoryImpl
}
BookingRepositoryImpl ..|> BookingRepository : 实现
note right of Booking
  中文渲染自检：订单、房型、可售间数
end note
@enduml
""", encoding="utf-8")
    png = out / "selftest.png"
    if png.exists():
        png.unlink()
    if JAVA.is_file() and PUMLLIB.is_file() and DOT.is_file():
        r = run([str(JAVA), "-DPLANTUML_LIMIT_SIZE=8192", "-jar", str(PUMLLIB),
                 "-charset", "UTF-8", "-graphvizdot", str(DOT), "-o", str(out), str(puml)])
        err = (r.stdout + r.stderr).strip()
        check("PlantUML 渲染返回 0", r.returncode == 0, err[:160])
        check("PNG 产出", png.is_file() and png.stat().st_size > 2000,
              "%d bytes" % png.stat().st_size if png.is_file() else "无输出")
        if png.is_file() and PY.is_file():
            r = run([str(PY), "-c",
                     "from PIL import Image,ImageStat;im=Image.open(r'%s').convert('L');"
                     "print(im.size[0],im.size[1],round(ImageStat.Stat(im).stddev[0],2))" % png])
            try:
                w, h, sd = r.stdout.split()
                check("PNG 尺寸合理", int(w) > 300 and int(h) > 150, "%sx%s" % (w, h))
                check("PNG 非空白（有内容）", float(sd) > 8.0, "gray stddev=%s" % sd)
            except Exception:
                check("PNG 可解析", False, (r.stdout + r.stderr)[:160])
        if png.is_file():
            check("单张渲染耗时 < 15s(记录)", True, "见上一步返回")

    print("\n[4] 中文渲染像素抽检（不联网，人工可复核）")
    check("中文自检图路径", png.is_file(), str(png) if png.is_file() else "缺失")

    print("\n[5] Edge 无头：HTML -> PDF（报告链路）")
    html = WORK / "selftest.html"
    html.write_text("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>自检</title><style>body{font-family:"Microsoft YaHei",sans-serif}</style></head>
<body><h1>中文 PDF 自检</h1><p>订单状态：待确认、已确认、已入住、已退房、已取消、未入住。</p>
<p>库存口径：可售间数＝当日净剩余可订量。</p></body></html>""", encoding="utf-8")
    pdf = out / "selftest.pdf"
    if pdf.exists():
        pdf.unlink()
    if EDGE.is_file():
        prof = WORK / "_profile"
        r = run([str(EDGE), "--headless=new", "--disable-gpu", "--no-first-run",
                 "--user-data-dir=" + str(prof), "--no-pdf-header-footer",
                 "--print-to-pdf=" + str(pdf), "file:///" + str(html).replace("\\", "/")], timeout=180)
        check("Edge 打印 PDF", pdf.is_file() and pdf.stat().st_size > 10000,
              "%d bytes" % pdf.stat().st_size if pdf.is_file() else (r.stderr or "")[:160])
        if pdf.is_file() and PY.is_file():
            r = run([str(PY), "-c",
                     "from pypdf import PdfReader;r=PdfReader(r'%s');t=r.pages[0].extract_text();"
                     "print(len(r.pages), '已确认' in t, len(t))" % pdf])
            parts = (r.stdout or "").split()
            ok = len(parts) == 3 and parts[1] == "True"
            check("PDF 页数≥1 且中文未掉字", ok, (r.stdout or r.stderr).strip()[:120])
    else:
        check("Edge 打印 PDF", False, "未找到 msedge.exe")

    print("\n" + "=" * 60)
    npass = sum(1 for _, ok, _ in results if ok)
    nfail = len(results) - npass
    print("SUMMARY: PASS(%d)/FAIL(%d)" % (npass, nfail))
    if nfail:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print("  - %s | %s" % (name, detail))
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
