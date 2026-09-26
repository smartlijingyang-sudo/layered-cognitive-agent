"""web-assistant turns the daytime episode governor on; other profiles stay off."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.core.execution.decision import Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.memory.episode import EpisodeFact
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.harness.profile.resolve.resolve import ResolvedPlugin, ResolvedProfile, resolve_profile
from lca.nodes.reflect.memory_extract.memory_extract import (
    ReflectMemoryExtractExecutor,
    setup,
)

_PLUGIN_ID = "phase.reflect.memory.extract"


def _plugin(resolved: ResolvedProfile, plugin_id: str) -> ResolvedPlugin:
    for plugin in resolved.plugins:
        if plugin.id == plugin_id:
            return plugin
    raise AssertionError(f"{plugin_id} not in resolved profile")


class _RecordingCtx:
    def __init__(self) -> None:
        self.provided: dict[str, object] = {}

    def provide(self, key: str, value: object) -> None:
        self.provided[key] = value


def _live_context(home: Path) -> NodeContext:
    runtime: dict[str, object] = {
        "agent_state": AgentState(trace_id="trace_live", task="我是架构师", budget=Budget()),
        "assistant_home_path": home,
    }
    return NodeContext(runtime=runtime, metadata={}, budget=None)


def _on_track_reflection() -> Reflection:
    return Reflection(
        reflection_id="refl_live",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={},
    )


@pytest.mark.asyncio
async def test_web_assistant_governor_appends_one_episode(tmp_path: Path) -> None:
    """The assistant profile's resolved switch is what appends the episode."""
    resolved = resolve_profile("profiles/web-assistant.yaml")
    plugin = _plugin(resolved, _PLUGIN_ID)
    assert plugin.config.governor_enabled is True

    ctx = _RecordingCtx()
    await setup.setup(ctx, plugin.config)
    executor = ctx.provided["reflect::phase.reflect.memory.extract"]
    assert isinstance(executor, ReflectMemoryExtractExecutor)

    await executor.node_execute(
        _live_context(tmp_path),
        NodeInput(port_values={"reflection": _on_track_reflection()}),
    )

    episodes = list((tmp_path / "memory" / "episodes").glob("*.json"))
    assert len(episodes) == 1
    fact = EpisodeFact.model_validate_json(episodes[0].read_text(encoding="utf-8"))
    assert fact.content == "用户身份：架构师"


def test_web_standard_leaves_episode_governor_off() -> None:
    """web-standard does not opt the same plugin into the governor."""
    resolved = resolve_profile("profiles/web-standard.yaml")
    config = _plugin(resolved, _PLUGIN_ID).config
    assert config.governor_enabled is not True
