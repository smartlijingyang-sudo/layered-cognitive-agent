"""GenAI semantic mapper 测试（ADR-0063 PR-10）。"""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    ToolInvoked,
)
from lca.infrastructure.observability.genai.llm import LlmGenAIMapper
from lca.infrastructure.observability.genai.registry import (
    build_default_registry,
)
from lca.infrastructure.observability.genai.tool import ToolGenAIMapper


def _scope() -> RunScope:
    return RunScope(trace_id="t", run_id="r")


def _stamped(seq: int, event: object) -> StampedEvent:
    return StampedEvent(seq=seq, ts=1000.0 + seq, scope=_scope(), event=event)  # type: ignore[arg-type]


def test_llm_mapper_emits_model_and_tokens() -> None:
    mapper = LlmGenAIMapper()
    stamped = _stamped(
        1,
        LlmCallCompleted(
            model="test-model",
            latency_ms=120,
            prompt_tokens=10,
            completion_tokens=20,
        ),
    )
    attrs = mapper.map(stamped)
    assert attrs["gen_ai.request.model"] == "test-model"
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.latency_ms"] == "120"
    assert attrs["gen_ai.usage.input_tokens"] == "10"
    assert attrs["gen_ai.usage.output_tokens"] == "20"


def test_tool_mapper_emits_name_and_invocation() -> None:
    mapper = ToolGenAIMapper()
    stamped = _stamped(
        1,
        ToolInvoked(
            tool_name="bash",
            invocation_id="inv-1",
            ok=True,
            latency_ms=50,
        ),
    )
    attrs = mapper.map(stamped)
    assert attrs["gen_ai.tool.name"] == "bash"
    assert attrs["gen_ai.tool.call.id"] == "inv-1"
    assert attrs["gen_ai.tool.call.ok"] == "true"
    assert attrs["gen_ai.tool.call.latency_ms"] == "50"


def test_default_registry_has_llm_and_tool_mappers() -> None:
    registry = build_default_registry()
    mappers = list(registry.all())
    assert len(mappers) == 2
    assert any(isinstance(m, LlmGenAIMapper) for m in mappers)
    assert any(isinstance(m, ToolGenAIMapper) for m in mappers)


def test_registry_dispatches_by_event_type() -> None:
    registry = build_default_registry()
    llm_event = _stamped(1, LlmCallCompleted(model="m"))
    mapper = registry.for_event(llm_event)
    assert isinstance(mapper, LlmGenAIMapper)


def test_registry_returns_none_for_unknown() -> None:
    from lca.contracts.models.observability.journal import TeamRunStarted

    registry = build_default_registry()
    stamped = _stamped(1, TeamRunStarted(team_id="t1"))
    assert registry.for_event(stamped) is None


def test_seam_provides_registry() -> None:
    from lca.plugins.seams.observability import genai as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-genai-semantic-mapper-seam"


def test_llm_mapper_registered() -> None:
    from lca.plugins import providers  # noqa: F401
    from lca.plugins.providers.observability import genai_llm as mod

    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-genai-llm-mapper"


def test_tool_mapper_registered() -> None:
    from lca.plugins import providers  # noqa: F401
    from lca.plugins.providers.observability import genai_tool as mod

    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-genai-tool-mapper"
