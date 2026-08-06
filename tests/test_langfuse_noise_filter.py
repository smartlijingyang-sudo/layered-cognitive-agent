"""Langfuse 视图噪音过滤 —— 词表判定 / detached 脚手架 / 桥接装配。

设计意图：Langfuse trace 树只保留有信息量的观测（run/agent/llm/tool/
业务事件），零 I/O 的框架内部 span（hook 边界、认知相位、memory、
transport.response）不进 Langfuse；console/jsonl/memory 后端不受影响。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lca.contracts.telemetry import EventName, SpanName
from lca.layer0_infra.observability import (
    ObservabilityHub,
    bind,
    detached_span,
    langfuse_span_visible,
    span,
)
from lca.layer0_infra.observability.langfuse_conventions import (
    LANGFUSE_HIDDEN_SPAN_NAMES,
    LANGFUSE_HIDDEN_SPAN_PREFIXES,
)
from lca.layer0_infra.observability.view import view_of

# ── 词表判定 ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "loop.phase.perceive",
        "loop.phase.think",
        "loop.phase.act",
        "loop.phase.reflect",
        "hook.on_start",
        "hook.on_complete",
        "memory.read",
        "memory.write",
        "transport.request",  # ADR-0037：父子链改由 delegation 承载，退回机制平面
        "transport.response",
    ],
)
def test_noise_spans_hidden(name: str) -> None:
    assert langfuse_span_visible(name) is False


@pytest.mark.parametrize(
    "name",
    [
        SpanName.RUN_TEAM.value,
        SpanName.RUN_AGENT.value,
        SpanName.TEAM_ROUND.value,  # 策略轮次包络保留
        SpanName.DELEGATION.value,  # 一等委派（承载成员父子链）
        SpanName.LLM_CHAT.value,
        SpanName.TOOL_EXECUTE.value,
        SpanName.DELEGATE_CACHE_HIT.value,
        SpanName.ERROR.value,
        EventName.DECISION_MADE.value,  # 瞬时事实 EVENT 观测
        EventName.RUN_INSIGHT.value,
    ],
)
def test_value_spans_visible(name: str) -> None:
    assert langfuse_span_visible(name) is True


def test_hidden_names_are_registered_span_names() -> None:
    """隐藏词表只能取已登记的 SpanName（防拼写漂移）。"""
    registered = {member.value for member in SpanName}
    assert set(LANGFUSE_HIDDEN_SPAN_NAMES) <= registered


def test_hidden_prefixes_are_framework_namespaces() -> None:
    assert LANGFUSE_HIDDEN_SPAN_PREFIXES == ("loop.phase.", "hook.")


# ── detached 脚手架：业务事件挂回 run 根 ────────────────


async def test_detached_span_does_not_capture_children() -> None:
    """detached span 只计时/落属性：块内发射仍挂外层父节点。"""
    exporter = InMemorySpanExporter()
    hub = ObservabilityHub([exporter])
    with (
        bind(hub),
        span(SpanName.RUN_AGENT, agent_role="测试角色"),
        detached_span(SpanName.LOOP_PHASE_REFLECT),
        span(SpanName.TOOL_EXECUTE, tool_name="calculator"),
    ):
        pass
    views = {v.name: v for v in map(view_of, exporter.get_finished_spans())}
    root = views[SpanName.RUN_AGENT.value]
    phase = views[SpanName.LOOP_PHASE_REFLECT.value]
    tool = views[SpanName.TOOL_EXECUTE.value]
    assert phase.parent_span_id == root.span_id  # 相位 span 仍挂在 run 根下
    assert tool.parent_span_id == root.span_id  # 块内 span 不被相位 span 捕获
    assert tool.parent_span_id != phase.span_id


async def test_attached_span_still_captures_children() -> None:
    """默认 attach 行为不变：嵌套 span 以当前 span 为父。"""
    exporter = InMemorySpanExporter()
    hub = ObservabilityHub([exporter])
    with (
        bind(hub),
        span(SpanName.RUN_AGENT, agent_role="测试角色"),
        span(SpanName.LOOP_PHASE_THINK),
        span(SpanName.LLM_CHAT, model="stub"),
    ):
        pass
    views = {v.name: v for v in map(view_of, exporter.get_finished_spans())}
    assert (
        views[SpanName.LLM_CHAT.value].parent_span_id
        == views[SpanName.LOOP_PHASE_THINK.value].span_id
    )


# ── 桥接装配：verbosity 决定过滤器 ─────────────────────


class _FakeLangfuse:
    """捕获构造参数的 Langfuse 替身（不触网）。"""

    last_kwargs: ClassVar[dict] = {}

    def __init__(self, **kwargs) -> None:
        _FakeLangfuse.last_kwargs = kwargs

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def _build_hub_with_fake_sdk(monkeypatch: pytest.MonkeyPatch, verbosity: str):
    langfuse_mod = pytest.importorskip("langfuse")
    monkeypatch.setattr(langfuse_mod, "Langfuse", _FakeLangfuse)

    from lca.layer0_infra.observability import create_observability
    from lca.layer0_infra.observability.policy import Verbosity
    from lca.layer0_infra.observability.settings import ObservabilitySettings

    cfg = ObservabilitySettings(
        backends="langfuse",
        verbosity=Verbosity(verbosity),
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",  # noqa: S106 —— 测试替身凭据，不触网
        langfuse_host="http://localhost:9",
    )
    return create_observability("langfuse", settings=cfg)


def test_bridge_applies_noise_filter_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _build_hub_with_fake_sdk(monkeypatch, "standard")
    try:
        callback = _FakeLangfuse.last_kwargs["should_export_span"]
        assert callback(SimpleNamespace(name="loop.phase.think")) is False
        assert callback(SimpleNamespace(name="hook.on_start")) is False
        assert callback(SimpleNamespace(name="memory.read")) is False
        assert callback(SimpleNamespace(name="llm.chat")) is True
        assert callback(SimpleNamespace(name="run.agent")) is True
    finally:
        hub.close()


def test_bridge_verbose_exports_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = _build_hub_with_fake_sdk(monkeypatch, "verbose")
    try:
        callback = _FakeLangfuse.last_kwargs["should_export_span"]
        assert callback(SimpleNamespace(name="loop.phase.think")) is True
        assert callback(SimpleNamespace(name="hook.on_start")) is True
        assert callback(SimpleNamespace(name="memory.read")) is True
    finally:
        hub.close()
