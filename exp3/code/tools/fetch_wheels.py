#!/usr/bin/env python
"""离线依赖抓取器（开发期工具，不属于运行期代码）。

用途：把 `requirements-dev.txt` 里的开发期依赖（及其传递依赖）的 wheel
下载到 `.wheels/`，使 `pip install --no-index --find-links .wheels` 可离线重建
虚拟环境。之所以自己抓，是因为本机 `pip` 的 HTTP 栈对 PyPI 会卡死，而
`urllib` 正常（实测 0.8s 取回 JSON）。

用法：
    python code/tools/fetch_wheels.py            # 默认读到 code/requirements-dev.txt
    python code/tools/fetch_wheels.py -o .wheels
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

JSON_API = "https://pypi.org/pypi/{name}/json"
PY_TAG, ABI_TAGS = "cp312", ("cp312", "abi3", "none")
PLAT_TAGS = ("win_amd64", "any")


def fetch_json(name: str) -> dict:
    """取 PyPI JSON API 的元数据（含 releases 与 requires_dist）。"""
    with urllib.request.urlopen(JSON_API.format(name=name), timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def vkey(version: str) -> tuple:
    """把 PEP 440 版本串转成可比较的元组（数字段优先于字母段）。"""
    parts = re.split(r"[.\-+]", version)
    out = []
    for part in parts:
        out.append((0, int(part)) if part.isdigit() else (1, part))
    return tuple(out)


def satisfies(version: str, spec: str) -> bool:
    """判断 version 是否满足 spec（支持 ==/!=/>=/<=/>/</~= 与逗号组合）。"""
    if not spec:
        return True
    current = vkey(version)
    for clause in spec.split(","):
        clause = clause.strip()
        if not clause:
            continue
        match = re.match(r"(~=|==|!=|>=|<=|>|<)\s*([\w.\-+]+)", clause)
        if not match:
            continue
        op, target = match.group(1), match.group(2)
        want = vkey(target)
        ok = {
            "==": current == want,
            "!=": current != want,
            ">=": current >= want,
            "<=": current <= want,
            ">": current > want,
            "<": current < want,
            "~=": current >= want and current[: len(want) - 1] == want[: len(want) - 1],
        }[op]
        if not ok:
            return False
    return True


def pick_wheel(name: str, version: str) -> str | None:
    """在指定版本的发行文件里挑一个 cp312/win_amd64（或纯 py3）的 wheel。"""
    data = fetch_json(name)
    for item in data["releases"].get(version, []):
        if not item["filename"].endswith(".whl"):
            continue
        fn = item["filename"]
        tags = fn[:-4].split("-")
        if len(tags) < 5:
            continue
        py, abi, plat = tags[-3], tags[-2], tags[-1]
        py_tags = py.split(".")
        if PY_TAG not in py_tags and "py3" not in py_tags and not py.startswith("cp3"):
            continue
        if abi not in ABI_TAGS:
            continue
        if not any(plat == t or plat.endswith("_" + t) or plat == "any" for t in PLAT_TAGS):
            continue
        return item["url"]
    return None


def marker_ok(marker: str) -> bool:
    """只实现本项目会遇到的标记分支（win32 / py3.12），其余一律拒绝。"""
    marker = marker.strip()
    if "extra" in marker:
        return False
    if "sys_platform" in marker:
        return ("win32" in marker) != ("!=" in marker)
    if "python_version" in marker:
        match = re.search(r'python_version\s*(==|!=|>=|<=|>|<)\s*[\'"]([\d.]+)[\'"]', marker)
        if not match:
            return True
        op, want = match.group(1), match.group(2)
        cur = vkey("3.12")
        target = vkey(want)
        return {
            "==": cur == target,
            "!=": cur != target,
            ">=": cur >= target,
            "<=": cur <= target,
            ">": cur > target,
            "<": cur < target,
        }[op]
    return True


def resolve(requirement: str, seen: dict, order: list) -> None:
    """递归解析一条依赖（含传递依赖与本地环境标记），结果写入 seen/order。"""
    match = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*(.*)$", requirement)
    if not match:
        return
    name = match.group(1).lower().replace("_", "-")
    spec = match.group(2).strip()
    if name in seen:
        return
    data = fetch_json(name)
    candidates = [v for v in data["releases"] if satisfies(v, spec)]
    candidates = [
        v for v in candidates if not re.search(r"[a-zA-Z]", v) or v == data["info"]["version"]
    ]
    if not candidates:
        raise SystemExit(f"× 找不到满足 {requirement} 的版本")
    version = max(candidates, key=vkey)
    url = pick_wheel(name, version)
    if not url:
        raise SystemExit(f"× {name} {version} 没有匹配 cp312/win_amd64 的 wheel")
    seen[name] = {"version": version, "url": url}
    # 传递依赖：带环境标记的先按本机（win32/py3.12）求值
    for dep in data["info"].get("requires_dist") or []:
        dep_spec, _, marker = dep.partition(";")
        if marker and not marker_ok(marker):
            continue
        resolve(dep_spec, seen, order)
    order.append(name)


def main() -> int:
    """命令行入口：读依赖清单，把 wheel 抓进输出目录。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--out", default=".wheels")
    parser.add_argument("-r", "--requirements", default="code/requirements-dev.txt")
    args = parser.parse_args()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    seen: dict[str, dict] = {}
    order: list[str] = []
    for line in Path(args.requirements).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            resolve(line, seen, order)

    for name in order:
        info = seen[name]
        filename = info["url"].rsplit("/", 1)[-1].split("#", 1)[0]
        target = out_dir / filename
        if target.exists():
            print(f"= {filename}")
            continue
        with urllib.request.urlopen(info["url"], timeout=60) as resp:
            target.write_bytes(resp.read())
        print(f"+ {filename} ({target.stat().st_size // 1024} KB)")

    print(f"\n共 {len(order)} 个 wheel → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
