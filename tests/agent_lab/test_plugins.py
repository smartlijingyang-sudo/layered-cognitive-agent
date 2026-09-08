"""Plugin system tests — discovery, compile-time + runtime hooks, EventSinkPlugin,
ObserverPlugin wiring into agent_loop.

Per plan acceptance criteria 1–6.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) Plugin discovery — every built-in plugin class is registered
# ---------------------------------------------------------------------------


def test_plugin_discovery_returns_builtin_kinds() -> None:
    from agent_lab.plugins import (
        EventSinkPlugin,
        ObserverPlugin,
        discover,
        get_plugin_class,
    )

    kinds = discover()
    assert "event_sink" in kinds
    assert "observer" in kinds
    assert get_plugin_class("event_sink") is EventSinkPlugin
    assert get_plugin_class("observer") is ObserverPlugin


def test_event_sink_and_observer_instantiate_with_config() -> None:
    """Each plugin can be instantiated via the class registry + config dict."""
    from agent_lab.plugins import EventSinkPlugin, ObserverPlugin, get_plugin_class

    sink_cls = get_plugin_class("event_sink")
    sink = sink_cls(
        name="sink1",
        kind="event_sink",
        config={"sink_id": "test", "session_fixture_name": "missing"},
    )
    assert isinstance(sink, EventSinkPlugin)
    obs_cls = get_plugin_class("observer")
    obs = obs_cls(name="obs1", kind="observer", config={"metric_prefix": "myprefix"})
    assert isinstance(obs, ObserverPlugin)
    assert obs.prefix == "myprefix"


# ---------------------------------------------------------------------------
# (2) PluginRef round-trips through the yaml loader
# ---------------------------------------------------------------------------


def test_loader_parses_plugins_block() -> None:
    from agent_lab.graphs import load_registry

    specs = load_registry("agent_loop")
    plugins = specs["agent_loop"].plugins
    assert len(plugins) >= 2
    kinds = {p.kind for p in plugins}
    ids = {p.id for p in plugins}
    assert "event_sink" in kinds
    assert "observer" in kinds
    assert "default_event_sink" in ids
    assert "default_observer" in ids


def test_loader_handles_absent_plugins_block() -> None:
    """Specs without a plugins: block get an empty tuple (backward-compat)."""
    from agent_lab.graphs import load_registry

    specs = load_registry("perceive")
    assert specs["perceive"].plugins == []


# ---------------------------------------------------------------------------
# (3) Compile-time hooks fire in spec order
# ---------------------------------------------------------------------------


def test_compile_hook_before_compile_fires_in_order() -> None:
    """Every plugin on the spec receives before_compile in spec order."""
    from agent_lab.plugins import (
        GraphPlugin,
        register_fixture_instance,
        unregister_fixture_instance,
    )

    calls: list[str] = []

    class _Recorder(GraphPlugin):
        def __init__(self, name: str, kind: str, tag: str, **kw) -> None:
            super().__init__(name=name, kind=kind, **kw)
            object.__setattr__(self, "tag", tag)

        def before_compile(self, spec, sub_registry=None):
            calls.append(self.tag)
            return spec

    a = _Recorder("__test_a__", "event_sink", "a")
    b = _Recorder("__test_b__", "event_sink", "b")
    register_fixture_instance("__test_a__", a)
    register_fixture_instance("__test_b__", b)
    try:
        from agent_lab.graph.compile import compile as compile_spec
        from agent_lab.graphs import load_registry

        specs = load_registry("agent_loop")
        # Inject two fixture-bound plugins ahead of the spec-declared ones.
        specs["agent_loop"] = specs["agent_loop"].model_copy(
            update={
                "plugins": [
                    *specs["agent_loop"].plugins,
                    __import__("agent_lab.graph.spec", fromlist=["PluginRef"]).PluginRef(
                        id="__test_a__", kind="event_sink"
                    ),
                    __import__("agent_lab.graph.spec", fromlist=["PluginRef"]).PluginRef(
                        id="__test_b__", kind="event_sink"
                    ),
                ]
            }
        )
        compile_spec(specs["agent_loop"], sub_registry=specs)
        # The recorder plugins are appended AFTER the spec-declared ones
        # in this test (so they run last). The recorder writes self.tag
        # ("a"/"b") to the calls list.
        assert "a" in calls and "b" in calls
        assert calls.index("a") < calls.index("b")
    finally:
        unregister_fixture_instance("__test_a__")
        unregister_fixture_instance("__test_b__")


def test_compile_bundle_carries_plugin_instances() -> None:
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.graphs import load_registry

    specs = load_registry("agent_loop")
    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)
    names = [p.name for p in bundle.plugin_instances]
    assert "default_event_sink" in names
    assert "default_observer" in names


# ---------------------------------------------------------------------------
# (4) EventSinkPlugin receives events from a full run
# ---------------------------------------------------------------------------


def test_event_sink_records_full_agent_loop_run() -> None:
    """Run the full agent_loop graph and assert the EventSinkPlugin captured
    events for at least one node_start + node_end + edge_fire + subgraph_enter
    + subgraph_exit. The plugin uses its in-memory fallback when no Session
    is configured — that fallback records into a private list we can read.
    """
    from agent_lab.adapters.lca_perceive import (
        register_fixture_hub,
        unregister_fixture_hub,
    )
    from agent_lab.plugins import EventSinkPlugin
    from agent_lab.primitives.artifact import Artifact, ArtifactKind
    from agent_lab.runtime.runner import run as run_graph
    from lca.plugins.composer.runtime.fixture.runtime_factory import (
        NullPerceiveHub as _NullHub,
    )

    # Stub LLM adapter to avoid network.
    class _StubAdapter:
        async def complete(self, prompt, **kw):
            from lca.contracts.models.core.conversation.llm import LLMResponse

            return LLMResponse(text="stub", tool_calls=[])

    specs = __import__("agent_lab.graphs", fromlist=["load_registry"]).load_registry(
        "perceive",
        "think",
        "reflect",
        "remember",
        "stop",
        "toolbox",
        "event_log",
        "mv_assemble",
        "effect_dispatch",
        "agent_loop",
    )
    # Swap perceive's build node to use a fixture hub (default
    # SequentialPerceiveHub constructor needs args we don't supply).
    for n in specs["perceive"].nodes:
        if n.id == "build":
            n.config["provider_config"] = {"fixture_hub_name": "null-hub"}
    for n in specs["think"].nodes:
        if n.id == "llm":
            n.config["provider_config"] = {
                "adapter_factory": {
                    "ref": "tests.agent_lab.fixtures.llm_stub:StubLlmAdapter",
                    "kwargs": {},
                }
            }
    # Swap perceive to a fixture hub.
    register_fixture_hub("null-hub", _NullHub())
    try:
        # Force the EventSinkPlugin to use a known in-memory sink we can
        # capture. Re-register with a fresh instance.
        sink_plugin = EventSinkPlugin(
            name="default_event_sink",
            kind="event_sink",
            config={"sink_id": "agent_loop"},
        )
        # Read the fallback list reference.
        fallback_sink = sink_plugin._sink()
        # Re-bind the bundle so it carries our re-registered plugin.
        # The bundle resolves plugins lazily — `register_instance()` puts
        # ours into the global map. Our plugin's `name` matches the
        # spec's `id`, so resolution returns ours first.
        from agent_lab.plugins import register_instance, unregister_instance

        register_instance(sink_plugin)
        try:
            trace = run_graph(
                specs["agent_loop"],
                initial={
                    "user_turn": Artifact(
                        kind=ArtifactKind.MESSAGE,
                        content=[{"role": "user", "content": "hi"}],
                    ),
                    "system": Artifact(kind=ArtifactKind.TEXT, content="sys"),
                    "history": Artifact(kind=ArtifactKind.MESSAGE, content=[]),
                    "config": Artifact(kind=ArtifactKind.FACT, content={"temperature": 0}),
                    "tools": Artifact(kind=ArtifactKind.FACT, content=[]),
                    "results": Artifact(kind=ArtifactKind.TEXT, content=""),
                    "state": Artifact(kind=ArtifactKind.FACT, content={"step": 0}),
                },
                sub_registry=specs,
            )
        finally:
            unregister_instance("default_event_sink")
        # The fallback sink captured every event the runner emitted.
        kinds_seen = {rec["data"]["event_kind"] for rec in fallback_sink.events}
        # EventSinkPlugin captures every hook event including the
        # semantic ones (on_decision / on_observation / on_reflection)
        # emitted by the runner's schema_ref-based fan-out.
        assert "node_start" in kinds_seen
        assert "node_end" in kinds_seen
        assert "edge_fire" in kinds_seen
        assert "subgraph_enter" in kinds_seen
        assert "subgraph_exit" in kinds_seen
        assert "on_decision" in kinds_seen
        assert "on_observation" in kinds_seen
        # Sanity: trace.events still includes the same events (backward-compat).
        trace_kinds = {ev.kind for ev in trace.events}
        assert "node_start" in trace_kinds
        assert "node_end" in trace_kinds
    finally:
        unregister_fixture_hub("null-hub")


# ---------------------------------------------------------------------------
# (5) ObserverPlugin metrics counters increment per node
# ---------------------------------------------------------------------------


def test_observer_plugin_counts_events() -> None:
    from agent_lab.plugins import ObserverPlugin

    # Reset the shared counter dict for deterministic assertions.
    ObserverPlugin._reset()
    obs = ObserverPlugin(name="counter_obs", kind="observer")
    from agent_lab.plugins.base import HookContext, HookEvent

    ctx = HookContext(event=HookEvent.NODE_START, spec_id="s")
    obs.dispatch(ctx)
    obs.dispatch(ctx)
    obs.dispatch(HookContext(event=HookEvent.NODE_END, spec_id="s"))
    obs.dispatch(HookContext(event=HookEvent.EDGE_FIRE, spec_id="s"))
    counters = ObserverPlugin.counters(name="counter_obs")
    assert counters.get("agent_lab.node_start") == 2
    assert counters.get("agent_lab.node_end.ok") == 1
    assert counters.get("agent_lab.edge_fire") == 1


# ---------------------------------------------------------------------------
# (6) Bind selector filters which events a plugin receives
# ---------------------------------------------------------------------------


def test_bind_filter_event_kind_only_receives_named_kind() -> None:
    from agent_lab.plugins.base import Bind, GraphPlugin, HookContext, HookEvent

    seen: list[HookEvent] = []

    class _OnlyStart(GraphPlugin):
        def on_event(self, ctx: HookContext) -> HookContext:
            seen.append(ctx.event)
            return ctx

    plug = _OnlyStart(
        name="only_start",
        kind="test",
        binds=(Bind(kind="event_kind", value="node_start"),),
    )
    plug.dispatch(HookContext(event=HookEvent.NODE_START, spec_id="s"))
    plug.dispatch(HookContext(event=HookEvent.NODE_END, spec_id="s"))
    assert seen == [HookEvent.NODE_START]


# ---------------------------------------------------------------------------
# (7) Hook failures are contained (mirrors LCA Session observer containment)
# ---------------------------------------------------------------------------


def test_hook_exceptions_are_contained() -> None:
    """A plugin that raises in its hook must not abort the runner.

    The dispatcher hook catches and logs; the ctx is returned unchanged
    so subsequent plugins still see it.
    """
    from agent_lab.plugins.base import (
        GraphPlugin,
        HookContext,
        HookEvent,
        fanout_hooks,
    )

    raised: list[str] = []
    followed: list[str] = []

    class _Boom(GraphPlugin):
        def on_event(self, ctx: HookContext) -> HookContext:
            raised.append("boom")
            raise RuntimeError("boom")

    class _After(GraphPlugin):
        def on_event(self, ctx: HookContext) -> HookContext:
            followed.append("after")
            return ctx

    # fanout_hooks catches per-plugin exceptions; the loop continues.
    fanout_hooks(
        [
            _Boom(name="boom", kind="test"),
            _After(name="after", kind="test"),
        ],
        HookEvent.NODE_START,
        HookContext(event=HookEvent.NODE_START),
    )
    assert raised == ["boom"]
    assert followed == ["after"]
