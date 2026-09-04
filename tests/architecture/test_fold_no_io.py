"""Fold 模块纯函数架构不变量 —— ADR-0185 §3.4 + §8.1 PR-3a2 收口。

不变量(对齐 deepseek-harness ``packages/core/session/src/request-header.ts``
纯函数语义):

- ``lca_kernel/events/fold.py`` 是 :func:`canonicalHeader` /
  :func:`headerEquals` / :func:`foldRequestHeader` 的纯函数集,无 I/O、无
  副作用。viewer / explain / replay / debug-run 全部依赖该纯函数性 fold,
  否则离线重建路径(``<run_id>.spine.jsonl`` 重放、sub-batch 增量 fold)
  被 I/O 污染就坏 C7(控制/观察分离)+ ADR-0185 §3.4 fold 语义。

验收基线(ADR-0185 §8.1 PR-0 合并前条目 2):
- ``rg "open(|Path(|read|write" lca_kernel/events/fold.py`` = 0
- ``import`` 不包含任何 I/O / 时钟 / 日志模块(``os`` / ``sys`` /
  ``pathlib`` / ``logging`` / ``datetime`` / ``time``)
- AST 扫不到对内置 ``open`` / ``print`` / ``Path`` 构造的调用

delete-when:N/A(纯加法;后续 PR-2 publisher / PR-3 viewer 重建都依赖
本模块纯函数性不变,作为长期架构守护)。
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from pathlib import Path

# 仓库根 = tests/architecture/ 的父父目录
_REPO_ROOT = Path(__file__).resolve().parents[2]

# fold 模块绝对路径(测试 SUT)
_FOLD_MODULE = _REPO_ROOT / "lca_kernel" / "events" / "fold.py"

# 测试文件自身路径(白名单:不在守范围内)
_THIS_TEST_FILE = Path(__file__).resolve()


# ── 工具 ──────────────────────────────────────────────────────────────────


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _rg(pattern: str, root: Path) -> list[str]:
    """Run ripgrep with relative paths; return list of matching lines.

    Empty list = no matches. Falls back to pathlib walk if rg is missing.
    """
    if not root.exists():
        return []
    if _have_ripgrep():
        result = subprocess.run(  # noqa: S603  # path is a constant binary
            [  # noqa: S607  # rg binary located via shutil.which()
                "rg",
                "--line-number",
                "--no-heading",
                "--color",
                "never",
                pattern,
                str(root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 1:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    compiled = re.compile(pattern)
    out: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                rel = path.relative_to(_REPO_ROOT)
                out.append(f"{rel}:{lineno}:{line}")
    return out


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ADR-0185 §8.1 PR-0 验收条目 2 原文禁词:open / Path( / read / write
# (Path( 也拦截 pathlib.Path 构造与 ``Path(__file__)`` 元数据读取)。
# 排除纯字符串字面量与 docstring 内的方法名提及(由 AST 扫描更精)。
_RAW_FORBIDDEN_TOKENS = re.compile(r"\bopen\(|\bPath\(|\bread\b|\bwrite\b")


# ── ADR-0185 §3.4 fold 纯函数性不变量 ──────────────────────────────────


class TestFoldNoIo:
    """fold 模块纯函数性 —— ADR-0185 §3.4 + §8.1 PR-0 收口条目。"""

    def test_fold_module_exists(self) -> None:
        """SUT 必须存在;否则 PR-0 spike 整体未落地。"""
        assert _FOLD_MODULE.exists(), (
            f"PR-3a2 SUT 缺失:{_FOLD_MODULE};lca_kernel/events/fold.py 未落地"
        )

    def test_fold_module_has_no_io_calls_in_source(self) -> None:
        """fold.py 源码无 ``open(`` / ``Path(`` / ``read`` / ``write`` 字面调用。

        对齐 ADR-0185 §8.1 PR-0 验收条目 2 原文。匹配行可能在 docstring 内
        是正常描述,本断言容忍:用 AST 二次扫描过滤掉 docstring / 注释。
        """
        assert _FOLD_MODULE.exists()
        source = _read_source(_FOLD_MODULE)

        # 第一层:rg 文本扫描(允许 docstring 误命中)
        raw_matches = _rg(_RAW_FORBIDDEN_TOKENS.pattern, _FOLD_MODULE)
        if not raw_matches:
            return

        # 第二层:AST 过滤,只保留真实可执行调用
        tree = ast.parse(source, filename=str(_FOLD_MODULE))
        docstring_linenos = _collect_docstring_linenos(tree)

        real_violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                target = _call_target_name(func)
                if target is None:
                    continue
                # open(...) 调用
                if target == "open":
                    real_violations.append(
                        f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:{node.lineno}: open(...) call"
                    )
                # pathlib.Path(...) 调用 — 包含 Path() 无参(指向 Path 类)
                elif target in {"Path"}:
                    real_violations.append(
                        f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:{node.lineno}: {target}(...) call"
                    )
            elif isinstance(node, ast.Attribute) and node.attr in {"read", "write"}:
                # 仅当属性访问的目标是显式标识符而非字符串字面量时计入
                if isinstance(node.value, ast.Name):
                    real_violations.append(
                        f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:"
                        f"{node.lineno}: .{node.attr} attribute access"
                    )

        # 过滤掉在 docstring / 注释内出现的匹配(行号重叠即视为提及非调用)
        non_doc_violations = [
            v
            for v in real_violations
            if not any(abs(_line_no(v) - d) <= 0 for d in docstring_linenos)
        ]

        assert not non_doc_violations, (
            "ADR-0185 §8.1 违规:fold.py 含 I/O 调用(对齐 dsh 纯函数语义)\n"
            + "\n".join(non_doc_violations[:5])
        )

    def test_fold_module_imports_no_io_or_clock_modules(self) -> None:
        """fold.py ``import`` 仅 stdlib typing/dataclasses,不引入 I/O / 时钟模块。

        守 import 子集:``os`` / ``sys`` / ``pathlib`` / ``logging`` /
        ``datetime`` / ``time`` / ``io`` 一律 0。这些是 I/O 与副作用的
        经典入口;fold 模块只能消费 ``Iterable`` / ``Mapping``,不接触
        任何 I/O。
        """
        assert _FOLD_MODULE.exists()
        source = _read_source(_FOLD_MODULE)

        forbidden_modules = (
            "os",
            "sys",
            "pathlib",
            "logging",
            "datetime",
            "time",
            "io",
            "subprocess",
            "shutil",
            "tempfile",
            "socket",
            "urllib",
        )
        tree = ast.parse(source, filename=str(_FOLD_MODULE))
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".", 1)[0]
                    if top in forbidden_modules:
                        violations.append(
                            f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:"
                            f"{node.lineno}: import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".", 1)[0]
                if top in forbidden_modules:
                    violations.append(
                        f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:"
                        f"{node.lineno}: from {node.module} import ..."
                    )

        assert not violations, (
            "ADR-0185 §3.4 违规:fold.py 不应 import I/O / 时钟模块\n" + "\n".join(violations[:5])
        )

    def test_fold_module_has_no_print_or_datetime_now_calls(self) -> None:
        """fold.py 无 ``print(`` / ``datetime.now(`` / ``logging.`` 等副作用调用。

        对齐 fold 模块 docstring 承诺:无 ``print`` / ``logging`` /
        ``datetime.now`` 等副作用。这是 ADR-0185 §3.4 §8.1 的硬性
        约束 ——viewer / explain / debug-run 的离线重建路径完全依赖 fold
        纯函数性。
        """
        assert _FOLD_MODULE.exists()
        source = _read_source(_FOLD_MODULE)
        tree = ast.parse(source, filename=str(_FOLD_MODULE))
        docstring_linenos = _collect_docstring_linenos(tree)

        violations: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _call_target_name(node.func)
            if target is None:
                continue
            # 精确拦截 print() / datetime.now() / time.time() / logging.*() 系列
            if target == "print" and node.lineno not in docstring_linenos:
                violations.append(
                    f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:{node.lineno}: print(...) call"
                )
            elif (
                target in {"now", "utcnow", "time", "sleep", "monotonic"}
                and node.lineno not in docstring_linenos
            ):
                # 拦截任何 now/utcnow/time/sleep/monotonic 调用;
                # 含 datetime.now()、time.time() 等
                violations.append(
                    f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:{node.lineno}: {target}(...) call"
                )

        assert not violations, (
            "ADR-0185 §8.1 违规:fold.py 含 print / 时钟 / sleep 等副作用调用\n"
            + "\n".join(violations[:5])
        )

    def test_fold_module_does_not_publish_to_event_bus(self) -> None:
        """fold.py AST 内无 ``EventBus`` / ``bus`` 标识符 + ``.publish(`` 调用。

        fold 是离线重建函数;若偷偷 publish 就破坏 ADR-0183 I-FW-BUS-1
        与 ADR-0185 §3.4 的"不动 production 行为"约束。AST 扫描过滤
        docstring 提及,只检测真实 ``Call`` 节点。
        """
        assert _FOLD_MODULE.exists()
        source = _read_source(_FOLD_MODULE)
        tree = ast.parse(source, filename=str(_FOLD_MODULE))
        docstring_linenos = _collect_docstring_linenos(tree)

        violations: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if node.lineno in docstring_linenos:
                continue
            # x.publish(...) — 任意对象的 publish 调用都禁
            if isinstance(node.func, ast.Attribute) and node.func.attr == "publish":
                violations.append(
                    f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:"
                    f"{node.lineno}: {ast.unparse(node.func)} call"
                )
            # EventBus(...) — 字面类构造
            elif isinstance(node.func, ast.Name) and node.func.id == "EventBus":
                violations.append(
                    f"{_FOLD_MODULE.relative_to(_REPO_ROOT)}:"
                    f"{node.lineno}: EventBus(...) literal construct"
                )

        assert not violations, (
            "ADR-0183 I-FW-BUS-1 违规:fold.py 不应调 EventBus.publish\n" + "\n".join(violations[:5])
        )


# ── helpers ──────────────────────────────────────────────────────────────


def _collect_docstring_linenos(tree: ast.AST) -> set[int]:
    """收集模块 + 函数 + 类 docstring 的起始行号集合。

    用于过滤 AST 扫到的"提及但非调用"——fold.py docstring 里会提到
    ``print`` / ``open`` / ``Path`` 是说明性文字,非真实调用。
    """
    linenos: set[int] = set()
    for node in ast.walk(tree):
        if _has_str_docstring(node):
            linenos.add(node.body[0].lineno)
    return linenos


def _has_str_docstring(node: ast.AST) -> bool:
    """模块 / 函数 / 类节点的首条 stmt 是字符串常量即视为 docstring。"""
    return bool(
        isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    )


def _call_target_name(func: ast.AST) -> str | None:
    """提取 ``Call.func`` 的可读函数名(支持 Name / Attribute 链)。"""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        # x.y.z(...) → 取末段 "z";datetime.now(...) → "now"
        return func.attr
    return None


def _line_no(rg_line: str) -> int:
    """``path:lineno:content`` 形式的行号抽取;AST 内已用 node.lineno,此函数仅供异常路径使用。"""
    parts = rg_line.split(":", 2)
    if len(parts) >= 2:
        try:
            return int(parts[1])
        except ValueError:
            return -1
    return -1
