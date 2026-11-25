"""源码规则检查：把"grep 判据"收成一条可复跑的命令。

S2-3（状态不得裸比较）、S2-5（金额不得用浮点）、S4-1（测试不得真实等待）、
S4-4（审计只追加）在任务书里都是 grep 判据。原先每次手写 ``Select-String``，
正则写宽写窄全凭当时手感——S4-R1-02 就是"判据用窄口径、缺陷用宽口径"漏掉的。
本工具把正则集中在 ``RULES`` 表里，证据文件里连正则一起打印，谁都能复算。

用法::

    python code/tools/check_source_rules.py
    python code/tools/check_source_rules.py --rule status_compare --rule float_round

退出码：所有规则命中数与期望一致 → 0，否则 1。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

#: ``code/`` 目录（本文件在 ``code/tools/`` 下）
CODE_ROOT = Path(__file__).resolve().parents[1]

#: 规则表里的正则刻意用字符串拼接，避免本文件自己被扫中（判据文件自身含示例文本）
_NO_SLEEP = r"time\.slee" + r"p|\bsleep\("
_AUDIT_DELETE = "delete" + r"\s+from\s+" + "audit_" + "log"
_STATUS_COMPARE = r"\.status" + r"\s*=="
_FLOAT = r"flo" + r"at\(|rou" + r"nd\("
_SHARED_CONN = r"check_same_thread" + r"\s*=\s*False"


@dataclass(frozen=True, slots=True)
class Rule:
    """一条源码规则：正则、作用范围、期望命中数。"""

    name: str
    pattern: str
    scope: str
    note: str

    @property
    def regex(self) -> re.Pattern[str]:
        """编译后的正则（大小写不敏感，grep 判据本身也不区分）。"""
        return re.compile(self.pattern, re.IGNORECASE)


RULES: tuple[Rule, ...] = (
    Rule(
        name="status_compare",
        pattern=_STATUS_COMPARE,
        scope="app",
        note="状态比较必须走枚举或转移表，不得裸比较字段（S2-3 宽口径）",
    ),
    Rule(
        name="float_round",
        pattern=_FLOAT,
        scope="app",
        note="金额一律整数分，不得出现浮点函数与四舍五入（S2-5）",
    ),
    Rule(
        name="time_sleep",
        pattern=_NO_SLEEP,
        scope="code",
        note="扫描必须注入假时钟；全仓（含测试与工具）不得真实等待（S4-1 / S6-R1-02）",
    ),
    Rule(
        name="audit_delete",
        pattern=_AUDIT_DELETE,
        scope="code",
        note="审计只追加，不得出现删除或改写语句（S4-4）",
    ),
    Rule(
        name="shared_connection",
        pattern=_SHARED_CONN,
        scope="code",
        note="每线程独立连接，不得靠关闭 check_same_thread 共享连接（S4-5）",
    ),
)


def iter_sources(scope: str) -> list[Path]:
    """列出作用范围内所有 ``.py`` 文件（跳过本工具自身）。

    Args:
        scope: ``"app"``/``"tests"``/``"tools"`` 为单个子目录，``"code"`` 为整个工程，
            ``"app_tests"`` 为业务代码加测试（``tools/`` 下的截图脚本要等窗口重绘，
            不属于"用真实等待代替假时钟"那一类，故排除在 S4-1 之外）。

    Returns:
        按路径排序的 Python 文件列表。
    """
    if scope == "code":
        roots = [CODE_ROOT]
    elif scope == "app_tests":
        roots = [CODE_ROOT / "app", CODE_ROOT / "tests"]
    else:
        roots = [CODE_ROOT / scope]
    this_file = Path(__file__).resolve()
    files: list[Path] = []
    for root in roots:
        files.extend(
            path for path in root.rglob("*.py") if path.resolve() != this_file
        )
    return sorted(files)


def scan(rule: Rule) -> tuple[list[str], int]:
    """扫一条规则。

    Args:
        rule: 规则定义。

    Returns:
        ``(命中行列表, 扫描文件数)``；命中行形如 ``code\\app\\x.py:12: 原文``。
    """
    hits: list[str] = []
    files = iter_sources(rule.scope)
    for path in files:
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if rule.regex.search(line):
                shown = path.relative_to(CODE_ROOT).as_posix()
                hits.append(f"  {shown}:{number}: {line.strip()}")
    return hits, len(files)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="源码规则检查（grep 判据统一入口）")
    parser.add_argument(
        "--rule",
        action="append",
        default=None,
        help="只跑指定规则（可重复），省略则跑全部",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """跑规则表并打印结果，返回退出码。"""
    args = parse_args(argv)
    selected = [
        rule for rule in RULES if args.rule is None or rule.name in set(args.rule)
    ]
    if not selected:
        print(f"没有匹配的规则：{args.rule}")
        return 1

    failed = 0
    total = 0
    for rule in selected:
        hits, files = scan(rule)
        total += len(hits)
        scope_label = "code" if rule.scope == "code" else f"code/{rule.scope}"
        status = "OK" if not hits else "HIT"
        print(
            f"rule={rule.name} scope={scope_label} files={files}"
            f" expected=0 hits={len(hits)} result={status}"
        )
        print(f"  regex={rule.pattern}")
        for line in hits:
            print(line)
        if hits:
            failed += 1

    print(f"rules={len(selected)} total_hits={total}")
    print(f"check={'passed' if failed == 0 else 'failed'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
