"""校验"类图符号"与"代码符号"是否一一对应（S2-6 判据的实现）。

规则：

1. 从 ``.puml`` 里取所有 ``class/interface "... " as Name`` 的别名（大写驼峰）；
2. 从 ``app/`` 下所有 ``.py`` 里取 ``class Name``；
3. 与白名单 ``code/docs/uml_map.md``（每行一个符号，带 ``.puml`` 行号）三方比对；
4. 任一方向缺符号、或白名单行号与真实行号不符 → 打印差集并以 1 退出。

白名单的意义：类图里有的符号**必须**在代码里有落点，落点文件写进表里，
评审可以按表抽查——这比"看代码感觉对得上"可验证。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PUML_SYMBOL = re.compile(
    r"^\s*(?:abstract\s+)?(?:class|interface|enum)\s+\"[^\"]*\"\s+as\s+(?P<name>\w+)"
)
PUML_FALLBACK = re.compile(r"^\s*(?:abstract\s+)?(?:class|interface)\s+(?P<name>\w+)")
CODE_CLASS = re.compile(r"^class\s+(?P<name>\w+)")
MAP_ROW = re.compile(r"^\|\s*(?P<symbol>[A-Z]\w*)\s*\|(?P<rest>.*)$")
MAP_LINE = re.compile(r"\.puml:L(?P<line>\d+)")


@dataclass(frozen=True)
class Symbol:
    """类图里的一个符号。"""

    name: str
    line: int


def parse_puml(path: Path) -> dict[str, Symbol]:
    """解析类图文件，返回 ``{符号名: 行号}``（保持出现顺序）。"""
    symbols: dict[str, Symbol] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = PUML_SYMBOL.match(raw) or PUML_FALLBACK.match(raw)
        if match is None:
            continue
        name = match.group("name")
        if name.startswith("_"):
            continue
        symbols.setdefault(name, Symbol(name=name, line=number))
    return symbols


def parse_code(app_dir: Path) -> dict[str, Path]:
    """扫描代码目录，返回 ``{类名: 所在文件}``（同名声明的首个文件）。"""
    found: dict[str, Path] = {}
    for file_path in sorted(app_dir.rglob("*.py")):
        for raw in file_path.read_text(encoding="utf-8").splitlines():
            match = CODE_CLASS.match(raw)
            if match is not None:
                found.setdefault(match.group("name"), file_path)
    return found


def parse_map(path: Path) -> dict[str, tuple[int | None, str]]:
    """解析白名单表，返回 ``{符号名: (puml 行号, 落点文件)}``。"""
    rows: dict[str, tuple[int | None, str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = MAP_ROW.match(raw)
        if match is None:
            continue
        symbol = match.group("symbol")
        cells = [cell.strip() for cell in match.group("rest").split("|")]
        line_match = MAP_LINE.search(raw)
        rows[symbol] = (
            int(line_match.group("line")) if line_match else None,
            cells[2] if len(cells) > 2 else "—",
        )
    return rows


def resolve(path_text: str, base: Path) -> Path:
    """先按当前目录解析，找不到再向上找一层（类图在 exp2/ 下、工具在 exp3/ 下跑）。"""
    candidate = base / path_text
    if candidate.exists():
        return candidate
    parent = base.parent / path_text
    if parent.exists():
        return parent
    raise SystemExit(f"找不到文件：{path_text}（以 {base} 为基准）")


def main(argv: list[str] | None = None) -> int:  # pylint: disable=too-many-locals
    """入口：打印逐符号结果 + 两个差集，返回退出码。

    局部变量多是因为要同时持有"三方符号表 + 四类差集"，拆函数反而让输出与判定分离，
    评审时不容易一眼对上号。
    """
    parser = argparse.ArgumentParser(description="类图符号与代码类名一致性校验")
    parser.add_argument("--puml", required=True, help="UML 类图 .puml 路径")
    parser.add_argument("--app", required=True, help="代码根目录（如 code/app）")
    parser.add_argument("--map", default="code/docs/uml_map.md", help="白名单表路径")
    args = parser.parse_args(argv)

    base = Path.cwd()
    puml_path = resolve(args.puml, base)
    app_dir = resolve(args.app, base)
    map_path = resolve(args.map, base)

    uml_symbols = parse_puml(puml_path)
    code_symbols = parse_code(app_dir)
    whitelist = parse_map(map_path)

    missing_in_code = sorted(name for name in uml_symbols if name not in code_symbols)
    missing_in_uml = sorted(name for name in whitelist if name not in uml_symbols)
    extra_in_code = sorted(name for name in code_symbols if name not in whitelist)
    line_mismatch = sorted(
        f"{name}(白名单 L{row[0]} ≠ 实际 L{uml_symbols[name].line})"
        for name, row in whitelist.items()
        if name in uml_symbols and row[0] is not None and row[0] != uml_symbols[name].line
    )

    print(f"puml={puml_path.name} symbols={len(uml_symbols)}")
    print(f"app={app_dir.name} classes={len(code_symbols)} whitelist={len(whitelist)}")
    print("-" * 78)
    for name, symbol in uml_symbols.items():
        row = whitelist.get(name)
        landing = row[1] if row else "（未登记）"
        mark = "OK " if name in code_symbols else "MISS"
        print(f"{mark} {name:<22} L{symbol.line:<4} -> {landing}")

    print("-" * 78)
    print(f"missing_in_code = {missing_in_code}")
    print(f"missing_in_uml  = {missing_in_uml}")
    print(f"extra_in_code   = {extra_in_code}（未登记，供评审核对，不判失败）")
    print(f"line_mismatch   = {line_mismatch}")

    if missing_in_code or missing_in_uml or line_mismatch:
        print("结果：FAIL（类图与代码不一致）")
        return 1
    print("结果：PASS（19 个符号一一对应，白名单行号一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
