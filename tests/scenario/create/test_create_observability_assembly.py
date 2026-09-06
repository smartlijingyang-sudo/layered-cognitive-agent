"""create_observability 装配：run 级投影器 + 可选 Langfuse 不阻断。

NOTE: 旧 ``create_observability(backends, settings, extra_projectors=...)``
工厂已被 plugin 装配面替代：
- console/jsonl/memory 后端 → ``lca.plugins.memory.journal_memory_provider`` 等
  seam 工厂，由 ``assemble_observability`` 从 ``PluginContext`` 注册表解析；
- Langfuse 桥接 → ``lca.plugins.observability.fact_reader_langfuse_provider`` 工厂；
- 投影器注入 → ``extra_projectors`` 已无对应入口；后端工厂接受
  ``projections=`` 关键字，调用方应在注册 seam 时传入。

本文件保留的 2 个测试都强依赖已删除 API（``create_observability``、
``hub.bridges``、``hub.close``）。按 ADR 决策跳过，并附说明，方便后续
基于 ``assemble_observability`` 重写。
"""

from __future__ import annotations

import pytest


class _Probe:
    """Mirror of the original probe; defined for type parity only."""


@pytest.mark.skip(
    reason='Removed in plugin-ification: ``create_observability("console", ...)`` '
    "is gone. Rewrite to ``assemble_observability(ctx, settings)`` after booting "
    "a plugin context with the journal_memory seam registered; verify by "
    "appending to ``bound.journal`` directly."
)
def test_extra_projectors_see_journal_events() -> None:
    pytest.fail("skipped — see skip reason")


@pytest.mark.skip(
    reason='Removed in plugin-ification: ``create_observability("console+langfuse", ...)`` '
    "is gone. ``hub.bridges`` had no replacement; Langfuse is now a fact_reader seam. "
    "Rewrite to assert the Langfuse plugin factory is skipped (not raised) when keys "
    "are blank, and that an in-process probe sees the recorded event."
)
def test_unavailable_langfuse_is_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.fail("skipped — see skip reason")
