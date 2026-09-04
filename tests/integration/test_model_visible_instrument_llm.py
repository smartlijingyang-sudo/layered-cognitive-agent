"""Diagnostic test for instrument_llm: verify the hook wiring at the LLM boundary.

If _resolve_model_visible_hook returns None (ctx 缺席 / 未挂载),
instrument_llm 退化为仅包 telemetry,spine events 不落;挂载成功时外层是
ModelVisibleHookAdapter,capture_pre_llm 产出 spine event。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from cordis import Context

from lca_kernel.events.bus import EventBus


@pytest.fixture
def booted_ctx() -> Any:
    """cordis Context with events.model_visible.publisher setup() run."""
    from pydantic import BaseModel

    from lca.plugins.events.publishers.model_visible.publisher import (
        setup as mv_setup,
    )

    captured: dict[str, Any] = {}

    class _StubPluginContext:
        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            captured[str(key)] = value

    class _Config(BaseModel):
        model_config = {"extra": "forbid"}

    setup_fn = getattr(mv_setup, "setup", mv_setup)
    asyncio.run(setup_fn(_StubPluginContext(), _Config()))

    ctx = Context()
    ctx.own_bindings.update(captured)
    return ctx


class _MockLLM:
    """Bare-minimum LLMAdapter stub; returns canned LLMResponse."""

    name = "mock"

    async def complete(self, prompt: str, **kwargs: Any) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(
            content="ok",
            text="ok",
            tool_calls=(),
            finish_reason="stop",
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    async def stream(self, prompt: str, **kwargs: Any):  # pragma: no cover
        if False:
            yield None


def test_instrument_llm_uses_new_hook_adapter(booted_ctx: Any) -> None:
    """instrument_llm should pick ModelVisibleHookAdapter when ctx has the hook."""
    from lca.infrastructure.observability.adapters import (
        TelemetryLLMAdapter,
    )
    from lca.plugins.composer.think.brain import instrument_llm
    from lca.plugins.events.hooks.model_visible.adapter import (
        ModelVisibleHookAdapter,
    )

    base = _MockLLM()
    out = instrument_llm(base, ctx=booted_ctx)

    print(f"\ninstrument_llm output type: {type(out).__name__}")

    # 新 wiring:外层是 ModelVisibleHookAdapter,或 TelemetryLLMAdapter
    # 包着内层 hook。
    if isinstance(out, ModelVisibleHookAdapter):
        print("✓ ModelVisibleHookAdapter chosen")
        return
    if isinstance(out, TelemetryLLMAdapter):
        inner = getattr(out, "_inner", None)
        print(f"  inner type: {type(inner).__name__ if inner else None}")
        if isinstance(inner, ModelVisibleHookAdapter):
            print("✓ ModelVisibleHookAdapter chosen (inner of telemetry)")
            return
    pytest.fail(f"Unexpected instrument_llm output type: {type(out).__name__}")


def test_instrument_llm_telemetry_only_when_ctx_absent() -> None:
    """No ctx → telemetry-only wiring (no model-visible decoration)."""
    from lca.infrastructure.observability.adapters import TelemetryLLMAdapter
    from lca.plugins.composer.think.brain import instrument_llm

    base = _MockLLM()
    out = instrument_llm(base, ctx=None)
    assert isinstance(out, TelemetryLLMAdapter), (
        "Without ctx we expect a bare TelemetryLLMAdapter (hook absent)."
    )
    assert getattr(out, "_inner", None) is base


def test_resolve_hook_on_real_cordis_ctx(booted_ctx: Any) -> None:
    """Direct test: _resolve_model_visible_hook finds hook on booted ctx."""
    from lca.plugins.composer.think.brain import _resolve_model_visible_hook

    resolved = _resolve_model_visible_hook(booted_ctx)
    assert resolved is not None, (
        f"_resolve_model_visible_hook returned None on booted ctx; "
        f"own_bindings keys: {list(booted_ctx.own_bindings.keys())}"
    )
    print(f"\nResolved hook: {type(resolved).__name__}")


def test_full_pipeline_publishes_spine_event(booted_ctx: Any) -> None:
    """Full path: instrument_llm → adapter.complete() → capture_pre_llm → publish.

    Bind a fake Session so publish_via_session succeeds; then check the bus
    delivery_snapshot for a spine.llm.request.header event.
    """
    from lca.plugins.composer.think.brain import instrument_llm
    from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
        CurrentReasonerPrompt,
    )
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )
    from lca_kernel.events.test_catalog import build_test_bus

    bus = build_test_bus()
    EventBus.set_default(bus)
    print(f"\nbus.registry.publishers keys: {len(bus.registry.publishers)} categories")

    class FakeSession:
        def __init__(self, bus: Any) -> None:
            self.bus = bus

        def append(self, payload: Any, *, producer: Any = None) -> Any:
            return self.bus.publish(payload, producer=producer)

    session = FakeSession(bus)
    session_token = set_publish_session(session)

    try:
        from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
            bind_current_cursor,
            get_current_cursor,
            reset_current_cursor,
        )
        from lca.plugins.events.hooks.model_visible.reasoner_prompt import (
            bind_current_reasoner_prompt,
            get_current_reasoner_prompt,
            reset_current_reasoner_prompt,
        )

        print(f"cursor provider returns: {get_current_cursor()}")
        print(f"prompt provider returns: {get_current_reasoner_prompt()}")

        llm = _MockLLM()
        wrapped = instrument_llm(llm, ctx=booted_ctx)
        print(f"wrapped type: {type(wrapped).__name__}")

        class _StubCursor:
            @property
            def snapshot(self) -> Any:
                return type(
                    "_Snap",
                    (),
                    {"run_id": "test-run", "step_index": 0, "incarnation": 1},
                )()

            def advance(self, *args: Any, **kwargs: Any) -> None:
                return None

        cursor_tok = bind_current_cursor(_StubCursor())
        prompt_tok = bind_current_reasoner_prompt(
            CurrentReasonerPrompt(
                step_id="step-001",
                template_id="t1",
                selector_decision_path="default",
                system_prompt_text="hello",
            )
        )

        try:
            pre_count = bus_count_published(bus)
            asyncio.run(wrapped.complete("test prompt", tools=[], messages=[]))
            post_count = bus_count_published(bus)
            print(f"published delta: {post_count - pre_count}")
            snap = bus.delivery_snapshot()
            for cat, stats in snap.items():
                if stats.get("published", 0) > 0:
                    print(f"  {cat}: {stats}")
        finally:
            reset_current_cursor(cursor_tok)
            reset_current_reasoner_prompt(prompt_tok)

        # Now check whether the new adapter's capture_post_llm published anything
        # (capture_pre_llm requires non-stable header; we provide one with tools)
        # The new adapter MUST have published the spine event if wired correctly.
        assert post_count > pre_count, (
            "wrapped.complete() did not publish any spine events — model-visible hook didn't fire."
        )
    finally:
        reset_publish_session(session_token)


def bus_count_published(bus: Any) -> int:
    snap = bus.delivery_snapshot()
    return sum(c.get("published", 0) for c in snap.values())
