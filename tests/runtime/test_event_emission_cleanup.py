"""ADR-0169 PR-26 ``lca.runtime.event_emission`` 清理验证。

ADR-0169 §D9 删除清单要求 ``event_emission.py`` 在 PR-26 阶段清理以下符号:

- ``_derive_step_completed`` —— 删除(POST_REFLECT 派生,业务迁 cursor 后废弃)
- ``make_journal_emitting_hook`` —— 删除(hook 范畴错误,ADR-0168.1 L19)
- ``JournalEmitFn`` —— 删除(仅 hook 内部使用)
- ``_derive_action_degraded`` —— 删除(make_journal_emitting_hook 删除后无调用方)

清理后模块保留空 shell 以容纳 ADR-0170 阶段辅助函数,新增派生走
ProjectionHost.register(def) 入口,不再 emit ``JournalEvent`` 直写路径。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVENT_EMISSION_PATH = REPO_ROOT / "lca" / "runtime" / "event_emission.py"


# ── 1. Module exports ────────────────────────────────────────────


def test_event_emission_module_loads() -> None:
    """``lca.runtime.event_emission`` 模块在 PR-26 后仍可加载(空 shell)。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    assert mod is not None
    # 模块必须有 __file__ 属性
    assert hasattr(mod, "__file__")


def test_event_emission_does_not_define_derive_step_completed() -> None:
    """``_derive_step_completed`` 在 PR-26 后不存在于 ``event_emission`` 模块字典里。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    assert "_derive_step_completed" not in mod.__dict__, (
        "ADR-0169 §D9 violation: _derive_step_completed still defined in event_emission.py"
    )


def test_event_emission_does_not_define_derive_action_degraded() -> None:
    """``_derive_action_degraded`` 在 PR-26 后不存在(make_journal_emitting_hook 删除后无调用方)。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    assert "_derive_action_degraded" not in mod.__dict__, (
        "ADR-0169 §D9 violation: _derive_action_degraded still defined in event_emission.py"
    )


def test_event_emission_does_not_define_make_journal_emitting_hook() -> None:
    """``make_journal_emitting_hook`` 在 PR-26 后不存在。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    assert "make_journal_emitting_hook" not in mod.__dict__, (
        "ADR-0169 §D9 violation: make_journal_emitting_hook still defined"
    )


def test_event_emission_does_not_define_journal_emit_fn() -> None:
    """``JournalEmitFn`` 在 PR-26 后不存在。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    assert "JournalEmitFn" not in mod.__dict__, (
        "ADR-0169 §D9 violation: JournalEmitFn still defined"
    )


def test_event_emission_does_not_define_derivations_table() -> None:
    """``_DERIVATIONS`` dict 不存在(原 hook 内部表,清理后必删)。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    assert "_DERIVATIONS" not in mod.__dict__, (
        "ADR-0169 §D9 violation: _DERIVATIONS table still defined"
    )


def test_event_emission_does_not_define_waterfall_type_alias() -> None:
    """``JournalEventWaterfallFn`` type alias 不存在(配套 hook 删除)。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    assert "JournalEventWaterfallFn" not in mod.__dict__, (
        "ADR-0169 §D9 violation: JournalEventWaterfallFn still defined"
    )


def test_event_emission_does_not_define_derivation_type_alias() -> None:
    """``Derivation`` type alias 不存在。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    assert "Derivation" not in mod.__dict__, (
        "ADR-0169 §D9 violation: Derivation type alias still defined"
    )


# ── 2. Imports fail for removed symbols ──────────────────────────


def test_removed_symbols_are_unimportable() -> None:
    """``from lca.runtime.event_emission import <removed>`` 抛 ImportError。

    每个被删符号都通过 ``exec`` 在子进程里尝试 import 并断言 ImportError。
    """
    removed = (
        "JournalEmitFn",
        "make_journal_emitting_hook",
        "_derive_action_degraded",
        "_derive_step_completed",
        "_DERIVATIONS",
        "JournalEventWaterfallFn",
        "Derivation",
    )
    code = "\n".join(
        f"""
try:
    from lca.runtime.event_emission import {name}
    print('IMPORTED:' + '{name}')
except ImportError as e:
    print('BLOCKED:' + '{name}:' + type(e).__name__)
"""
        for name in removed
    )
    result = subprocess.run(  # noqa: S603 — trusted local subprocess
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    for line in lines:
        if line.startswith("IMPORTED:"):
            name = line.removeprefix("IMPORTED:")
            pytest.fail(
                f"ADR-0169 §D9 violation: {name} still importable from lca.runtime.event_emission"
            )
        assert line.startswith("BLOCKED:"), f"unexpected subprocess output: {line!r}"


# ── 3. Static grep gate ─────────────────────────────────────────


def test_event_emission_source_file_does_not_define_removed_functions() -> None:
    """源文件不含 ``def _derive_step_completed`` / ``def make_journal_emitting_hook`` 等定义。

    AST 解析 → 排除 docstring / 注释 → 静态门禁。
    """
    import ast

    source = EVENT_EMISSION_PATH.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(source)
    defined: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.append(target.id)
    forbidden = {
        "_derive_step_completed",
        "_derive_action_degraded",
        "make_journal_emitting_hook",
        "JournalEmitFn",
        "JournalEventWaterfallFn",
        "Derivation",
        "_DERIVATIONS",
    }
    leaked = forbidden & set(defined)
    assert not leaked, f"ADR-0169 §D9 violation: event_emission.py still defines: {sorted(leaked)}"


def test_event_emission_source_does_not_reference_coord_emit_phase() -> None:
    """源文件不含 ``coord.emit_phase`` 残留。"""
    import ast

    source = EVENT_EMISSION_PATH.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "emit_phase"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "coord"
        ):
            found.append(f"line {node.lineno}: {ast.unparse(node.func)}")
    assert not found, (
        "ADR-0169 §D9 violation: event_emission.py still calls coord.emit_phase:\n"
        + "\n".join(found)
    )


# ── 4. Runtime package re-exports ───────────────────────────────


def test_lca_runtime_does_not_reexport_journal_emit_fn() -> None:
    """``lca.runtime`` 不再 re-export ``JournalEmitFn``。"""
    runtime_pkg = importlib.import_module("lca.runtime")
    assert "JournalEmitFn" not in runtime_pkg.__dict__, (
        "ADR-0169 §D9 violation: lca.runtime still re-exports JournalEmitFn"
    )


def test_lca_runtime_does_not_reexport_make_journal_emitting_hook() -> None:
    """``lca.runtime`` 不再 re-export ``make_journal_emitting_hook``。"""
    runtime_pkg = importlib.import_module("lca.runtime")
    assert "make_journal_emitting_hook" not in runtime_pkg.__dict__, (
        "ADR-0169 §D9 violation: lca.runtime still re-exports make_journal_emitting_hook"
    )


# ── 5. Hook registry no longer wires journal hook ───────────────


def test_hook_registry_simple_does_not_import_make_journal_emitting_hook() -> None:
    """``lca.plugins.runtime.hook_registry`` 不再 import ``make_journal_emitting_hook``。

    PR-26 清理:``build_simple_hook_registry`` 直接返回 ``CordisHookRegistry``,
    不再注册派生 hook。
    """
    import ast

    path = REPO_ROOT / "lca" / "plugins" / "runtime" / "hook_registry.py"
    source = path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "event_emission" in node.module:
            for alias in node.names:
                found.append(f"{node.module}:{alias.name}")
    assert not found, (
        "ADR-0169 §D9 violation: hook_registry.py still imports from event_emission:\n"
        + "\n".join(found)
    )


# ── 6. Static grep for any residual reference to removed symbols ──


def test_no_residual_reference_to_removed_symbols_in_lca() -> None:
    """``lca/`` 全树不含 ``_derive_step_completed`` / ``_derive_action_degraded`` 标识符引用。

    docstring / 注释 / 字符串里的提及通过 AST 排除。
    """
    import ast

    lca_root = REPO_ROOT / "lca"
    forbidden = {
        "_derive_step_completed",
        "_derive_action_degraded",
        "make_journal_emitting_hook",
    }
    offenders: list[str] = []
    for py in lca_root.rglob("*.py"):
        # 跳过本测试自身的注释提及
        if py == Path(__file__).resolve():
            continue
        try:
            source = py.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden:
                # 排除局部变量同名(空 catch)
                offenders.append(f"{py.relative_to(REPO_ROOT)}:{node.lineno}: {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in forbidden:
                offenders.append(f"{py.relative_to(REPO_ROOT)}:{node.lineno}: ...{node.attr}")
    assert not offenders, (
        "ADR-0169 §D9 violation: lca/ still references removed symbols:\n" + "\n".join(offenders)
    )


# ── 7. Module docstring documents cleanup rationale ─────────────


def test_event_emission_docstring_documents_pr26_cleanup() -> None:
    """模块 docstring 必须说明 PR-26 清理内容,避免后续 PR 重新引入已删符号。"""
    mod = importlib.import_module("lca.runtime.event_emission")
    doc = mod.__doc__ or ""
    assert "ADR-0169" in doc, (
        "event_emission module docstring must reference ADR-0169 §D9 cleanup rationale"
    )
    assert "_derive_step_completed" in doc, "docstring must mention _derive_step_completed deletion"
    assert "make_journal_emitting_hook" in doc, (
        "docstring must mention make_journal_emitting_hook deletion"
    )
