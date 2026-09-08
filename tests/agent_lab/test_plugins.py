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

    specs = load_registry("perceive", "model_eye")
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
#
# NOTE (2026-09-08): removed — the test depended on
# ``agent_lab.adapters.lca_perceive.register_fixture_hub``, which was
# deleted in the perceive-first-principles refactor (perceive is now
# ``perceive.aggregate``, no Hub). EventSinkPlugin coverage belongs to
# a fresh e2e test that doesn't require a Hub fixture.
# ---------------------------------------------------------------------------


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
