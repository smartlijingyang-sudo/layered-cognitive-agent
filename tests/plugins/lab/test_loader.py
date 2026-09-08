"""Tests for the LCA lab plugin loader.

PR-A.3 — verifies that lca.plugins.lab.internal.loader correctly loads
all @plugin carriers and populates _LAB_HOOKS.
"""

import pytest
from lca.plugins.lab.internal.loader import (
    get_instance,
    list_ids,
    load_all,
    registered_lca_packages,
    resolve_plugin,
    reset_for_tests,
)


class MockRef:
    """Mock PluginRef with id and kind attributes."""

    def __init__(self, id: str, kind: str = "unknown"):
        self.id = id
        self.kind = kind


def test_load_all_populates_hooks():
    """load_all() should import all hook carriers and populate _LAB_HOOKS."""
    reset_for_tests()
    assert len(list_ids()) == 0, "Should start empty"

    load_all()

    ids = list_ids()
    assert len(ids) > 0, "Should populate _LAB_HOOKS"
    # Verify the 9 expected hook handlers are loaded
    assert "lab.hook.events" in ids
    assert "lab.hook.observers" in ids
    assert "lab.hook.parsers" in ids
    assert "lab.hook.semantic_router" in ids
    assert "lab.hook.control_slots" in ids
    assert "lab.hook.observation" in ids
    assert "lab.hook.memory_extract" in ids
    assert "lab.hook.tool_guard" in ids
    assert "lab.hook.session_log_emitter" in ids


def test_load_all_idempotent():
    """load_all() should be idempotent."""
    reset_for_tests()

    load_all()
    ids1 = list_ids()

    load_all()
    ids2 = list_ids()

    assert ids1 == ids2, "Should be idempotent"


def test_get_instance_returns_handler():
    """get_instance() should return the handler instance for a slot id."""
    reset_for_tests()
    load_all()

    instance = get_instance("lab.hook.events")
    assert instance is not None, "Should return instance"
    # Verify it has hook methods (GraphPlugin interface)
    assert hasattr(instance, "matches")
    assert hasattr(instance, "dispatch")
    assert hasattr(instance, "on_event")


def test_get_instance_returns_none_for_unknown():
    """get_instance() should return None for unknown slot ids."""
    reset_for_tests()
    load_all()

    instance = get_instance("lab.hook.unknown")
    assert instance is None


def test_resolve_plugin_by_id():
    """resolve_plugin() should resolve by ref.id."""
    reset_for_tests()
    load_all()

    ref = MockRef("lab.hook.events")
    instance = resolve_plugin(ref)

    assert instance is not None
    assert instance is get_instance("lab.hook.events")


def test_resolve_plugin_warns_on_miss(caplog):
    """resolve_plugin() should warn and return None on miss."""
    reset_for_tests()
    load_all()

    ref = MockRef("lab.hook.nonexistent", "some_kind")

    # Should log a warning and return None
    import logging
    with caplog.at_level(logging.WARNING):
        result = resolve_plugin(ref)
    
    assert result is None
    assert "cannot resolve plugin ref" in caplog.text
    assert "lab.hook.nonexistent" in caplog.text


def test_registered_lca_packages():
    """registered_lca_packages() should list all lab plugin packages on disk."""
    reset_for_tests()

    packages = registered_lca_packages()

    # Should include the 9 hook carrier packages
    assert "lca.plugins.lab.events" in packages
    assert "lca.plugins.lab.observers" in packages
    assert "lca.plugins.lab.parsers" in packages
    # internal is also registered but doesn't have a @plugin carrier
    assert "lca.plugins.lab.internal" in packages


def test_loader_closed_set_matches_filesystem():
    """The loader's known_subpackages should match registered_lca_packages
    minus 'internal' (which has no @plugin carrier)."""
    reset_for_tests()
    load_all()

    from lca.plugins.lab.internal.loader import known_subpackages

    # known_subpackages returns module paths with .plugin suffix
    # registered_lca_packages returns package paths without .plugin suffix
    known = set(pkg.rsplit('.plugin', 1)[0] for pkg in known_subpackages())
    registered = set(registered_lca_packages()) - {"lca.plugins.lab.internal"}

    # All known packages should be registered
    assert known.issubset(registered), f"Unknown packages: {known - registered}"
    # All registered hook carriers should be known
    assert registered.issubset(known), f"Unknown registered: {registered - known}"


def test_graph_compile_uses_loader():
    """graph.compile should use the loader to resolve plugins."""
    reset_for_tests()
    from agent_lab.graph.compile import _resolve_plugins
    from agent_lab.graph.spec import InfoEdgeSpec, PluginRef

    # Create a minimal spec with a plugin ref
    spec = InfoEdgeSpec(
        id="test",
        nodes=[],
        edges=[],
        grants=[],
        plugins=[PluginRef(id="lab.hook.events", kind="event_sink", binds=(), config={})],
    )

    # _resolve_plugins should trigger load_all() and resolve the plugin
    plugins = _resolve_plugins(spec)

    assert len(plugins) == 1
    assert plugins[0] is get_instance("lab.hook.events")


def test_runner_uses_loader():
    """runner should use the loader to resolve plugins."""
    # Skip if cordis is not available (full LCA environment required)
    pytest.importorskip("cordis")
    
    reset_for_tests()
    from agent_lab.runtime.runner import _Runner
    from agent_lab.graph.spec import InfoEdgeSpec, PluginRef
    from agent_lab.graph.compile import CompiledGraphBundle

    # Create a minimal runner with a plugin ref
    spec = InfoEdgeSpec(
        id="test",
        nodes=[],
        edges=[],
        grants=[],
        plugins=[PluginRef(id="lab.hook.events", kind="event_sink", binds=(), config={})],
    )

    bundle = CompiledGraphBundle(
        spec_id="test",
        plan_hash="abc123",
        spec_dump={},
        bindings=[],
        layers=[],
        subgraph_calls=[],
        plugin_instances=[],  # No pre-loaded plugins
    )

    from agent_lab.runtime.runner import ExecutionTrace

    runner = _Runner(
        spec=spec,
        bundle=bundle,
        initial={},
        sub_registry={},
        trace=ExecutionTrace(),
        subgraph_path="",
    )

    # _plugins() should trigger load_all() and resolve the plugin
    plugins = runner._plugins()

    assert len(plugins) == 1
    assert plugins[0] is get_instance("lab.hook.events")


def test_no_deprecation_warnings_after_pr_a3():
    """Importing agent_lab.plugins.base should not emit DeprecationWarning."""
    reset_for_tests()
    import warnings
    import sys

    # Remove agent_lab.plugins.base from sys.modules to force re-import
    if "agent_lab.plugins.base" in sys.modules:
        del sys.modules["agent_lab.plugins.base"]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import agent_lab.plugins.base

        # Should not have any DeprecationWarning
        deprecation_warnings = [
            warning for warning in w
            if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 0, (
            f"Should not emit DeprecationWarning, but got: {deprecation_warnings}"
        )
