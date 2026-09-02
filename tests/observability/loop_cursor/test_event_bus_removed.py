"""ADR-0169 PR-30:cordis 双词表收口 — CordisEventBus 业务包装必须删除。

cordis 双词表收口(评审 §S4 处方 + §D9 删除清单):

- ``lca/cognition/event_bus.py`` 整模块删除;CordisEventBus 业务包装不可
  再存在;所有 cordis 事件总线职责已转移到 ``EventDescriptor.derive()``
  + spine 单写(L10)。

- ``run_narrative.py`` 的引用:本仓库实际是
  ``lca/infrastructure/observability/narrative/run_narrative.py``,内容
  仅为 span 诊断渲染(``format_span_line`` / ``is_milestone_span``),
  与 cordis 业务总线职责无关,保留 —— 仅固化"该路径不应再承载 cordis
  事件名派生 / emit 入口"的语义,确保 ADR §D9 收口后无法被回填。

门禁脚本: ``scripts/check_cordis_event_derivation.py`` 的
``_check_cordis_event_bus_removed`` 与本测试互相强化。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest


def test_event_bus_module_removed() -> None:
    """``lca.cognition.event_bus`` 必须因 ``ModuleNotFoundError`` 而 import 失败。

    收口证据:ModuleNotFoundError 而不是 ImportError 表明模块真的不存在,
    不是模块存在但出现导入错误。
    """
    # 主动从 sys.modules 移除以防被前面的测试意外缓存;否则 import 不会
    # 重新解析,即便文件已删除也可能命中缓存。
    sys.modules.pop("lca.cognition.event_bus", None)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("lca.cognition.event_bus")


def test_cordis_event_bus_class_symbol_unavailable() -> None:
    """``CordisEventBus`` 与 ``cordis_event_bus`` 工厂符号必须不可 import。"""
    sys.modules.pop("lca.cognition.event_bus", None)

    with pytest.raises(ModuleNotFoundError):
        from lca.cognition.event_bus import CordisEventBus  # noqa: F401

    with pytest.raises(ModuleNotFoundError):
        from lca.cognition.event_bus import cordis_event_bus  # noqa: F401


def test_run_narrative_does_not_emit_cordis_event_names() -> None:
    """``run_narrative.py`` 不得承载 cordis 事件名派生 / emit 入口。

    仓库中 ``lca/infrastructure/observability/narrative/run_narrative.py``
    仅含 span 诊断渲染(``format_span_line`` / ``is_milestone_span``),
    职责非 cordis 事件总线。本测试固化"该路径不得新增 cordis emit 入口"
    的语义:任何 ``ctx.emit`` / ``EventDescriptor.derive`` 调用出现即视为
    违规(防止 PR-30 收口后被回填)。
    """
    repo_root = Path(__file__).resolve().parents[3]
    target = (
        repo_root / "lca" / "infrastructure" / "observability" / "narrative" / "run_narrative.py"
    )
    assert target.exists(), f"unexpected: span diagnostic helper missing: {target}"

    text = target.read_text(encoding="utf-8")
    forbidden = ("ctx.emit", "EventDescriptor.derive", "EventDescriptor(")
    for marker in forbidden:
        assert marker not in text, (
            f"{target.name} 不得承载 cordis 事件名派生 / emit 入口 "
            f"(found {marker!r});ADR-0169 §D9 + 评审 §S4 双词表收口。"
        )


def test_check_cordis_event_derivation_script_reports_pass() -> None:
    """``scripts/check_cordis_event_derivation.py`` 在 PR-30 收口后必须返回 0。

    该脚本同时校验:
    1. 业务代码无 ``ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')``;
    2. ``EventDescriptor`` 含 ``cordis_name`` 字段;
    3. ``lca/cognition/event_bus.py`` 不再承载 CordisEventBus 类。
    """
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "check_cordis_event_derivation.py"
    assert script.exists(), f"missing static guard script: {script}"

    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=False,
    )
    assert result.returncode == 0, (
        f"PR-30 cordis gate FAILED:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
