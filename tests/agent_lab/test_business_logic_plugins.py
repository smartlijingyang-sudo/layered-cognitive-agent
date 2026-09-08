"""Business-logic plugin tests — the four plugins that drive cognitive / tool
behaviour decisions live entirely in plugin land now.

Each test calls the plugin directly with a HookContext carrying the
relevant artifact and asserts the rewritten payload.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) ParseDecisionPlugin — LLMResponse → Decision.action_type
# ---------------------------------------------------------------------------


def test_parse_decision_tool_call_action_type() -> None:
    """Tool calls → action_type = 'call_tool'."""
    from agent_lab.plugins import ParseDecisionPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = ParseDecisionPlugin()
    artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_1",
            "action_type": "respond",  # initial wrong value (heuristic fallback)
            "response_text": "",
            "tool_calls": [{"name": "bash", "arguments": {"command": "ls"}}],
        },
        schema_ref="decision.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_DECISION,
        node_id="parse",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    assert new_ctx.payload["artifact"].content["action_type"] == "call_tool"


def test_parse_decision_respond_action_type() -> None:
    """Plain text without tool calls → action_type = 'respond'."""
    from agent_lab.plugins import ParseDecisionPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = ParseDecisionPlugin()
    artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_2",
            "action_type": "call_tool",
            "response_text": "Hello world",
            "tool_calls": [],
        },
        schema_ref="decision.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_DECISION,
        node_id="parse",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    assert new_ctx.payload["artifact"].content["action_type"] == "respond"


def test_parse_decision_refuse_action_type() -> None:
    """Empty text + empty tool_calls → action_type = 'refuse'."""
    from agent_lab.plugins import ParseDecisionPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = ParseDecisionPlugin()
    artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_3",
            "action_type": "respond",
            "response_text": "",
            "tool_calls": [],
        },
        schema_ref="decision.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_DECISION,
        node_id="parse",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    assert new_ctx.payload["artifact"].content["action_type"] == "refuse"


# ---------------------------------------------------------------------------
# (2) ObservationRenderPlugin — receipt → observation text
# ---------------------------------------------------------------------------


def test_observation_render_success() -> None:
    from agent_lab.plugins import ObservationRenderPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = ObservationRenderPlugin()
    artifact = Artifact(
        kind=ArtifactKind.MANIFEST,
        content={"status": "ok", "tool": "bash", "result": "hi"},
        schema_ref="observation.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_OBSERVATION,
        node_id="integrate",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    assert new_ctx.payload["artifact"].content["text"] == "[tool:bash] hi"


def test_observation_render_error() -> None:
    from agent_lab.plugins import ObservationRenderPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = ObservationRenderPlugin()
    artifact = Artifact(
        kind=ArtifactKind.MANIFEST,
        content={"status": "error", "error": "boom"},
        schema_ref="observation.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_OBSERVATION,
        node_id="integrate",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    assert new_ctx.payload["artifact"].content["text"] == "[tool-error] boom"


# ---------------------------------------------------------------------------
# (3) MemoryExtractPlugin — Reflection → memory_candidates
# ---------------------------------------------------------------------------


def test_memory_extract_lesson_only() -> None:
    from agent_lab.plugins import MemoryExtractPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = MemoryExtractPlugin()
    artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "reflection_id": "refl_1",
            "verdict": "ON_TRACK",
            "lesson": "always validate user input",
            "correction": None,
            "extra": {},
        },
        schema_ref="reflection.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_REFLECTION,
        node_id="extract",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    items = new_ctx.payload["memory_candidates"]["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "lesson"
    assert items[0]["text"] == "always validate user input"


def test_memory_extract_three_kinds() -> None:
    """All three candidate kinds (lesson, correction, extra) emit."""
    from agent_lab.plugins import MemoryExtractPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = MemoryExtractPlugin()
    artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "reflection_id": "refl_2",
            "verdict": "REVISED",
            "lesson": "use shorter prompts",
            "correction": {
                "decision_id": "dec_2",
                "action_type": "respond",
            },
            "extra": {"note": "applied across runs"},
        },
        schema_ref="reflection.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_REFLECTION,
        node_id="extract",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    kinds = {c["kind"] for c in new_ctx.payload["memory_candidates"]["items"]}
    assert kinds == {"lesson", "correction", "extra"}


# ---------------------------------------------------------------------------
# (4) ToolDispatchGuardPlugin — empty tool name → denied
# ---------------------------------------------------------------------------


def test_tool_dispatch_guard_denies_none_name() -> None:
    from agent_lab.plugins import ToolDispatchGuardPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = ToolDispatchGuardPlugin()
    artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_d1",
            "action_type": "call_tool",
            "tool_calls": [{"name": None, "arguments": {}}],
        },
        schema_ref="decision.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_DECISION,
        node_id="dispatch",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    assert new_ctx.payload["artifact"].content["denied"] is True


def test_tool_dispatch_guard_passes_real_name() -> None:
    from agent_lab.plugins import ToolDispatchGuardPlugin
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    plugin = ToolDispatchGuardPlugin()
    artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_d2",
            "action_type": "call_tool",
            "tool_calls": [{"name": "bash", "arguments": {"command": "ls"}}],
        },
        schema_ref="decision.v1",
    )
    ctx = HookContext(
        event=HookEvent.ON_DECISION,
        node_id="dispatch",
        payload={"artifact": artifact},
    )
    new_ctx = plugin.dispatch(ctx)
    # Plugin should NOT mutate; ``denied`` field absent.
    assert "denied" not in new_ctx.payload["artifact"].content
    # ctx is unchanged.
    assert new_ctx is ctx


# ---------------------------------------------------------------------------
# (5) end-to-end: removed (2026-09-08).
#
# test_runner_end_to_end_parse_decision_rewrites depended on
# ``agent_lab.adapters.lca_perceive`` (the PerceiveHub provider + fixture
# registry), which was deleted in the perceive-first-principles refactor.
# Perceive now uses ``perceive.aggregate`` (pure composition, no Hub).
# Coverage of ParseDecisionPlugin's rewrite path belongs to a fresh e2e
# test that does not require a Hub fixture.
# ---------------------------------------------------------------------------
