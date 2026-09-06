"""I-FW-EMIT-1 + ADR-0194 §7 L2 / ADR-0195 P-L7: 事实生产单入口守门。

``exception.caught`` EP 只允许一个 emitter —
``lca.infrastructure.observability.spine.exception_emit.emit_exception_caught``。

Loop 热路径 durable 事实应经 ``FactGateway`` (``append_catalog_bound`` /
``publish_ep_bound``) 或 ``harness.session.emit``(catalog rollback in
``fact_gateway.py``),不得新增平行 ``publish_via_session`` /
``append_journal_event`` / 直接 ``Session.append`` 调用。
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOT = _REPO_ROOT / "lca"
_LOOP_SCAN_ROOT = _REPO_ROOT / "lca" / "loop"
_SSOT_POSIX = "lca/infrastructure/observability/spine/exception/exception_emit.py"

# L2 / P-L7: loop 层允许的事实生产面(其余文件不得新增下列 pattern)。
_LOOP_FACT_SSOT_FILES: frozenset[str] = frozenset(
    {
        "lca/loop/fact_gateway.py",
    }
)
_LOOP_FACT_BASELINE_DEBT: frozenset[str] = frozenset()
_LOOP_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    "publish_via_session",
    "append_journal_event",
    "Session.append",
    "spine_reflector",
)


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _find_emit_defs() -> list[tuple[str, int, str, str]]:
    """Return ``[(relpath, lineno, kind, enclosing)]`` for every
    ``emit_exception_caught`` definition outside the SSOT module.

    Uses AST on each ``.py`` file under ``lca/`` to detect module-level
    functions and class methods named ``emit_exception_caught``.
    """
    if not _SCAN_ROOT.exists():
        return []
    results: list[tuple[str, int, str, str]] = []
    for path in sorted(_SCAN_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(_REPO_ROOT).as_posix()
        if rel == _SSOT_POSIX:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "emit_exception_caught" not in source:
            continue
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "emit_exception_caught":
                    results.append((rel, node.lineno, "function", "<module>"))
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == "emit_exception_caught"
                    ):
                        results.append((rel, item.lineno, "method", node.name))
    return results


def _code_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("#"):
        return ""
    return line.split("#", 1)[0]


def _find_loop_fact_violations() -> frozenset[str]:
    """Return loop/*.py paths using forbidden fact-production patterns."""
    offenders: set[str] = set()
    if not _LOOP_SCAN_ROOT.exists():
        return frozenset()
    allowed = _LOOP_FACT_SSOT_FILES | _LOOP_FACT_BASELINE_DEBT
    for py in sorted(_LOOP_SCAN_ROOT.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = py.relative_to(_REPO_ROOT).as_posix()
        if rel in allowed:
            continue
        try:
            lines = py.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        if any(
            pattern in _code_line(line) for line in lines for pattern in _LOOP_FORBIDDEN_PATTERNS
        ):
            offenders.add(rel)
    return frozenset(offenders)


# COMPAT(delete-when: note-3 PR-1 + PR-2 落地, _find_emit_defs() 返回空列表;
# 删除 _PENDING_DEBT_FILES 后下方 test 内的 xfail 分支一并移除)
# tracking: 2026-09-03-3-seam-emit-single-entry.md PR-1/PR-2
_PENDING_DEBT_FILES: frozenset[str] = frozenset(
    {
        "lca/contracts/protocols/runtime/envelope_emitter.py",
        "lca/runtime/envelope_emitter.py",
    }
)


class TestIFwEmit1:
    """I-FW-EMIT-1: ``emit_exception_caught`` 只有一个生产定义。"""

    def test_emit_exception_caught_single_definition(self) -> None:
        """SSOT emitter 是唯一 ``def emit_exception_caught``。

        当前 3 处平行 emitter 是已知债务(note-3 PR-1/PR-2 负责删除),
        本测试以 ``pytest.xfail`` 跟踪。债务清零后 xfail 自动变 xpass
        → 必须移除 ``_PENDING_DEBT_FILES`` 和本测试的 xfail 分支。
        """
        violations = _find_emit_defs()

        # Split into known-debt vs unexpected violations
        known = [v for v in violations if v[0] in _PENDING_DEBT_FILES]
        unexpected = [v for v in violations if v[0] not in _PENDING_DEBT_FILES]

        # New regressions (outside tracked debt) are hard failures
        assert not unexpected, (
            "I-FW-EMIT-1 违规: 发现 _PENDING_DEBT_FILES 之外的平行 emitter\n"
            + "\n".join(f"  {rel}:{line} ({kind} in {enc})" for rel, line, kind, enc in unexpected)
        )

        # Known debt: xfail until PR-1/PR-2 lands
        if known:
            debt_summary = "\n".join(
                f"  {rel}:{line} ({kind} in {enc})" for rel, line, kind, enc in known
            )
            pytest.xfail(
                "I-FW-EMIT-1 已知债务(note-3 PR-1/PR-2 清理):\n" + debt_summary,
            )

    def test_rg_emit_exception_caught_baseline(self) -> None:
        """rg 辅助断言:``def emit_exception_caught`` 在 SSOT 之外 = 0(目标)。

        当前有 3 处平行定义(已知债务)。本测试用 ripgrep 做快速辅助校验,
        与 AST 扫描互补。债务清零后断言直接 PASS。
        """
        if not _have_ripgrep():
            pytest.skip("ripgrep not installed")
        import subprocess

        result = subprocess.run(
            [  # noqa: S607  # rg binary located via shutil.which()
                "rg",
                "--count-matches",
                r"^(\s*async\s+)?def emit_exception_caught\b",
                "--glob",
                "*.py",
                "lca/",
            ],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        # rg --count-matches prints "file:count" per file
        total = 0
        ssot_count = 0
        per_file: dict[str, int] = {}
        for line in result.stdout.strip().splitlines():
            if ":" not in line:
                continue
            path_part, count_str = line.rsplit(":", 1)
            count = int(count_str)
            per_file[path_part] = count
            total += count
            if path_part == _SSOT_POSIX:
                ssot_count = count

        non_ssot = total - ssot_count
        assert ssot_count >= 1, "SSOT emitter missing from exception_emit.py"
        if non_ssot != 0:
            pytest.xfail(
                f"I-FW-EMIT-1: 预期 0 个非 SSOT emitter,实际 {non_ssot}。 per_file={per_file}"
            )


class TestL2LoopFactSingleEntry:
    """ADR-0194 §7 L2 / ADR-0195 P-L7: loop 热路径事实经 FactGateway 缝。"""

    def test_loop_no_new_fact_production_bypass(self) -> None:
        """除 SSOT + 已知债外,loop 不得新增平行事实生产 import/usage。"""
        offenders = sorted(_find_loop_fact_violations())
        assert offenders == [], (
            "L2/P-L7 新增违规:lca/loop/** 出现 FactGateway 之外的 fact 生产面:\n"
            + "\n".join(f"  - {p}" for p in offenders)
            + "\n使用 append_catalog_bound / publish_ep_bound;已知债见 _LOOP_FACT_BASELINE_DEBT。"
        )

    def test_loop_fact_baseline_debt_unchanged(self) -> None:
        """Known-debt set is empty after ADR-0194 P1 journal migration."""
        current_debt = {rel for rel in _LOOP_FACT_BASELINE_DEBT if (_REPO_ROOT / rel).exists()}
        assert current_debt == _LOOP_FACT_BASELINE_DEBT
