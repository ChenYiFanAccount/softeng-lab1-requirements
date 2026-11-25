"""源码规模统计工具：物理行 / 非空非注释 / 扣 docstring（主口径）。

口径由 P0 评审裁定：**空行、纯注释行、docstring 行全部扣除**，剩下的才算
"有效行"。报告与交付说明一律以第三列（effective）为主口径，另外两列只是
为了让读者看清三种口径差多少。

用法（在 exp3/ 下）::

    python code/tools/count_loc.py                    # 三列统计 app/tests/tools
    python code/tools/count_loc.py --root code/app    # S7-5 判据用法，只统计 app
    python code/tools/count_loc.py --csv code/docs/loc.csv

输出示例::

    app    files=17  phys=2223  code=1797  effective=1317
    tests  files=10  phys=1180  code=1006  effective=886
    tools  files=5   phys=560   code=470   effective=392
    total  files=32  phys=3963  code=3273  effective=2595
"""

from __future__ import annotations

import argparse
import ast
import csv
import sys
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_SECTIONS: tuple[str, ...] = ("app", "tests", "tools")
DEFAULT_CODE_ROOT = Path("code")
DEFAULT_CSV = Path("code/docs/loc.csv")


def code_root() -> Path:
    """定位 `code/` 目录：优先当前工作目录，其次本文件上两级。"""
    candidate = Path.cwd() / "code"
    if candidate.is_dir():
        return candidate
    return Path(__file__).resolve().parents[1]


def docstring_line_numbers(tree: ast.AST) -> set[int]:
    """收集模块/类/函数首条语句若是字符串常量时占据的行号。"""
    lines: set[int] = set()
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, owners):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr):
            continue
        value = first.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        end = getattr(first, "end_lineno", None) or first.lineno
        lines.update(range(first.lineno, end + 1))
    return lines


def count_file(path: Path) -> tuple[int, int, int]:
    """返回单个文件的（物理行、非空非注释、扣 docstring）。"""
    text = path.read_text(encoding="utf-8")
    physical = len(text.splitlines())
    try:
        tree = ast.parse(text, filename=str(path))
        skip = docstring_line_numbers(tree)
    except SyntaxError:
        skip = set()
    code_lines = 0
    effective = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        code_lines += 1
        if number in skip:
            continue
        effective += 1
    return physical, code_lines, effective


def count_section(directory: Path) -> tuple[int, int, int, int]:
    """汇总一个目录下所有 `.py` 文件。"""
    if not directory.is_dir():
        return 0, 0, 0, 0
    files = sorted(directory.rglob("*.py"))
    physical = code_lines = effective = 0
    for path in files:
        one, two, three = count_file(path)
        physical += one
        code_lines += two
        effective += three
    return len(files), physical, code_lines, effective


def format_row(name: str, stats: tuple[int, int, int, int]) -> str:
    """把一组统计格式化成一行表格文本。"""
    files, physical, code_lines, effective = stats
    return (
        f"{name:<6} files={files:<3} phys={physical:<5} "
        f"code={code_lines:<5} effective={effective:<5}"
    )


def write_csv(path: Path, rows: Sequence[tuple[str, tuple[int, int, int, int]]]) -> None:
    """把三列统计写成 CSV，便于报告直接引用。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["section", "files", "physical_lines", "non_blank_non_comment", "effective_lines"]
        )
        for name, stats in rows:
            files, physical, code_lines, effective = stats
            writer.writerow([name, files, physical, code_lines, effective])


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="统计有效代码行（扣空行/注释/docstring）")
    parser.add_argument("--code-root", type=Path, default=None, help="code 目录，默认自动定位")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="直接统计某个目录（S7-5 判据用法，如 code/app）",
    )
    parser.add_argument(
        "--sections",
        nargs="+",
        default=list(DEFAULT_SECTIONS),
        help="要统计的子目录，默认 app tests tools",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="CSV 输出路径（全量模式默认 code/docs/loc.csv；--root 模式默认不写）",
    )
    parser.add_argument("--no-csv", action="store_true", help="只打印不写 CSV")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    """入口：打印三列统计，写 CSV，返回退出码。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.code_root or code_root()
    rows: list[tuple[str, tuple[int, int, int, int]]] = []
    if args.root is not None:
        rows.append((args.root.name or "root", count_section(args.root)))
    else:
        for name in args.sections:
            rows.append((name, count_section(root / name)))
    totals = (
        sum(stats[0] for _, stats in rows),
        sum(stats[1] for _, stats in rows),
        sum(stats[2] for _, stats in rows),
        sum(stats[3] for _, stats in rows),
    )
    for name, stats in rows:
        print(format_row(name, stats))
    print(format_row("total", totals))
    print("口径：effective = 非空 且 非纯注释 且 非 docstring（报告主口径）")
    csv_path = args.csv
    if csv_path is None and args.root is None and not args.no_csv:
        csv_path = DEFAULT_CSV
    if csv_path is not None and not args.no_csv:
        write_csv(csv_path, rows)
        print(f"csv={csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
