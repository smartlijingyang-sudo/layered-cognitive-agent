"""I-FW-EMIT-1: ``emit_exception_caught`` 单入口守门。

ADR-0169 + note ``2026-09-03-3-seam-emit-single-entry.md`` PR-3:

``exception.caught`` EP 只允许一个 emitter —
``lca.infrastructure.observability.spine.exception_emit.emit_exception_caught``。
任何其它 ``def emit_exception_caught`` 都是平行实现,必须删除。

守护范围:

- ``lca/`` 下所有 ``.py`` 文件,排除 SSOT 模块本身
- 检测 module-level function 和 class method
- Protocol stub(``EnvelopeEmitter.emit_exception_caught``)也在守护范围:
  note 要求其删除(keyword 参数面无法承载 ``ExceptionRecord``)

当前债:

- ``lca/contracts/protocols/runtime/envelope_emitter.py`` Protocol stub
- ``lca/runtime/envelope_emitter.py`` SpineEnvelopeEmitter 实现
- ``lca/plugins/events/publishers/spine_reflector_runtime/plugin.py`` 函数

这三处由 note-3 PR-1/PR-2 负责删除(另一个 agent 的 WIP)。本测试以
xfail 跟踪,一旦清理完成 xfail 自动变 xpasse → 移除 xfail 标记。
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOT = _REPO_ROOT / "lca"
_SSOT_POSIX = "lca/infrastructure/observability/spine/exception_emit.py"


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


# COMPAT(delete-when: note-3 PR-1 + PR-2 落地, _find_emit_defs() 返回空列表;
# 删除 _PENDING_DEBT_FILES 后下方 test 内的 xfail 分支一并移除)
# tracking: 2026-09-03-3-seam-emit-single-entry.md PR-1/PR-2
_PENDING_DEBT_FILES: frozenset[str] = frozenset(
    {
        "lca/contracts/protocols/runtime/envelope_emitter.py",
        "lca/runtime/envelope_emitter.py",
        "lca/plugins/events/publishers/spine_reflector_runtime/plugin.py",
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
