"""Behavioral tests for ``filter_external_default_disabled``.

Per ADR-0199 §3.4 + §10 Phase 5 + I-HPC-11 (信任默认拒绝): plugins with
``external_kind`` in ``{"mcp", "sandbox", "worker"}`` default to disabled
in addition to ``source``-based untrusted filtering (P3-04). The active
profile is the admission authority — explicit profile provenance is
required for any non-``inprocess`` plugin.

Tests use ``ResolvedPlugin.id`` and ``ResolvedPlugin.module`` as the
only contract surface; the surrounding definition / config fields are
populated by the resolve pipeline, not the filter.
"""

from __future__ import annotations

import ast
import warnings

import pytest

from lca.harness.profile.resolve.external_filter import (
    ExternalFilterError,
    filter_external_default_disabled,
)
from lca.harness.profile.resolve.resolve import (
    ResolvedPlugin,
    _disabled_stub,
)

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------


def _make_plugin(
    plugin_id: str,
    module: str,
    *,
    source: str = "profiles/test.yaml",
    disabled: bool = False,
) -> ResolvedPlugin:
    """Build a minimal ``ResolvedPlugin`` for filter tests.

    The definition / config fields are not consulted by the filter — it
    only reads ``id`` and ``module``. The stub definition keeps the
    dataclass type contract honored.
    """
    return ResolvedPlugin(
        id=plugin_id,
        module=module,
        definition=_disabled_stub(plugin_id, module),
        config={},
        config_sources={},
        disabled=disabled,
        source=source,
        index=0,
    )


def _inprocess(plugin_id: str = "lca.plugins.inproc") -> ResolvedPlugin:
    return _make_plugin(
        plugin_id=plugin_id,
        module="lca.plugins.inproc",
    )


def _mcp(plugin_id: str = "ext.mcp_plugin", module: str = "ext.mcp_plugin") -> ResolvedPlugin:
    return _make_plugin(
        plugin_id=plugin_id,
        module=module,
    )


def _sandbox(
    plugin_id: str = "ext.sandbox_plugin",
    module: str = "ext.sandbox_plugin",
) -> ResolvedPlugin:
    return _make_plugin(
        plugin_id=plugin_id,
        module=module,
    )


def _worker(
    plugin_id: str = "ext.worker_plugin",
    module: str = "ext.worker_plugin",
) -> ResolvedPlugin:
    return _make_plugin(
        plugin_id=plugin_id,
        module=module,
    )


# ---------------------------------------------------------------------------
# inprocess default enabled
# ---------------------------------------------------------------------------


def test_inprocess_plugins_all_kept() -> None:
    """All inprocess plugins survive the filter — they are trusted by default."""
    plugins = (
        _make_plugin("lca.plugins.a", "lca.plugins.a"),
        _make_plugin("lca.plugins.b", "lca.plugins.b"),
        _make_plugin("lca.plugins.c", "lca.plugins.c"),
    )
    kept = filter_external_default_disabled(plugins, profile_path="profiles/x.yaml")
    assert kept == plugins


# ---------------------------------------------------------------------------
# mcp / sandbox / worker default disabled
# ---------------------------------------------------------------------------


def test_mcp_plugins_filtered_when_not_explicitly_enabled() -> None:
    """MCP plugin without profile provenance → dropped with warning."""
    with pytest.warns(UserWarning, match="external-default plugins filtered"):
        kept = filter_external_default_disabled(
            (_mcp(),),
            profile_path="profiles/x.yaml",
            external_kind_by_module={"ext.mcp_plugin": "mcp"},
        )
    assert kept == ()


def test_sandbox_plugins_filtered_when_not_explicitly_enabled() -> None:
    """Sandbox plugin without profile provenance → dropped with warning."""
    with pytest.warns(UserWarning, match="external-default plugins filtered"):
        kept = filter_external_default_disabled(
            (_sandbox(),),
            profile_path="profiles/x.yaml",
            external_kind_by_module={"ext.sandbox_plugin": "sandbox"},
        )
    assert kept == ()


def test_worker_plugins_filtered_when_not_explicitly_enabled() -> None:
    """Worker plugin without profile provenance → dropped with warning."""
    with pytest.warns(UserWarning, match="external-default plugins filtered"):
        kept = filter_external_default_disabled(
            (_worker(),),
            profile_path="profiles/x.yaml",
            external_kind_by_module={"ext.worker_plugin": "worker"},
        )
    assert kept == ()


# ---------------------------------------------------------------------------
# Mixed inprocess + external
# ---------------------------------------------------------------------------


def test_mixed_inprocess_and_external() -> None:
    """Inprocess kept; external dropped; preserved order."""
    plugins = (
        _make_plugin("lca.plugins.a", "lca.plugins.a"),
        _mcp(),
        _make_plugin("lca.plugins.b", "lca.plugins.b"),
        _sandbox(),
    )
    with pytest.warns(UserWarning, match="external-default"):
        kept = filter_external_default_disabled(
            plugins,
            profile_path="profiles/x.yaml",
            external_kind_by_module={
                "ext.mcp_plugin": "mcp",
                "ext.sandbox_plugin": "sandbox",
            },
        )
    assert [p.id for p in kept] == ["lca.plugins.a", "lca.plugins.b"]


# ---------------------------------------------------------------------------
# Explicit enable via profile provenance
# ---------------------------------------------------------------------------


def test_external_plugin_kept_when_profile_path_matches_module_name() -> None:
    """Profile path contains the plugin module name → kept (explicit enable)."""
    plugin = _make_plugin("ext.mcp_plugin", "ext.mcp_plugin")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_external_default_disabled(
            (plugin,),
            profile_path="profiles/ext_mcp_plugin.yaml",
            external_kind_by_module={"ext.mcp_plugin": "mcp"},
        )
    assert kept == (plugin,)
    assert not [w for w in captured if "external-default" in str(w.message)]


def test_external_plugin_kept_when_profile_path_matches_plugin_id() -> None:
    """Profile path contains the plugin id → kept (explicit enable)."""
    plugin = _make_plugin("ext.sandbox_plugin", "ext.sandbox_plugin")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_external_default_disabled(
            (plugin,),
            profile_path="profiles/ext.sandbox_plugin.yaml",
            external_kind_by_module={"ext.sandbox_plugin": "sandbox"},
        )
    assert kept == (plugin,)
    assert not [w for w in captured if "external-default" in str(w.message)]


# ---------------------------------------------------------------------------
# Warning emission contract
# ---------------------------------------------------------------------------


def test_filtered_plugins_emit_warning() -> None:
    """Filter call with at least one drop emits one UserWarning."""
    with pytest.warns(UserWarning, match="ADR-0199"):
        filter_external_default_disabled(
            (_mcp(),),
            profile_path="profiles/x.yaml",
            external_kind_by_module={"ext.mcp_plugin": "mcp"},
        )


def test_warning_lists_filtered_plugin_ids() -> None:
    """Warning text mentions every dropped plugin id and its kind label."""
    plugins = (
        _make_plugin("ext.alpha", "ext.alpha"),
        _make_plugin("ext.beta", "ext.beta"),
    )
    with pytest.warns(UserWarning) as record:
        filter_external_default_disabled(
            plugins,
            profile_path="profiles/x.yaml",
            external_kind_by_module={
                "ext.alpha": "mcp",
                "ext.beta": "worker",
            },
        )
    messages = [str(w.message) for w in record]
    assert any("ext.alpha" in msg for msg in messages)
    assert any("ext.beta" in msg for msg in messages)
    assert any("kind=mcp" in msg for msg in messages)
    assert any("kind=worker" in msg for msg in messages)


def test_warn_filtered_false_silences_warning() -> None:
    """``warn_filtered=False`` opt-out keeps the filter but silences the warning."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_external_default_disabled(
            (_mcp(),),
            profile_path="profiles/x.yaml",
            external_kind_by_module={"ext.mcp_plugin": "mcp"},
            warn_filtered=False,
        )
    assert kept == ()
    assert not [w for w in captured if "external-default" in str(w.message)]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_output() -> None:
    """Empty plugin tuple → empty tuple, no warning."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_external_default_disabled((), profile_path="profiles/x.yaml")
    assert kept == ()
    assert not [w for w in captured if "external-default" in str(w.message)]


def test_filter_preserves_order_of_kept_plugins() -> None:
    """Kept subset preserves the input order (deterministic)."""
    plugins = (
        _make_plugin("lca.plugins.a", "lca.plugins.a"),
        _make_plugin("ext.alpha", "ext.alpha"),
        _make_plugin("lca.plugins.b", "lca.plugins.b"),
        _make_plugin("ext.beta", "ext.beta"),
    )
    with pytest.warns(UserWarning):
        kept = filter_external_default_disabled(
            plugins,
            profile_path="profiles/x.yaml",
            external_kind_by_module={
                "ext.alpha": "mcp",
                "ext.beta": "worker",
            },
        )
    assert [p.id for p in kept] == ["lca.plugins.a", "lca.plugins.b"]


def test_default_kind_is_inprocess_when_module_not_in_map() -> None:
    """Modules missing from ``external_kind_by_module`` are treated as inprocess."""
    plugin = _make_plugin("lca.plugins.unknown", "lca.plugins.unknown")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_external_default_disabled(
            (plugin,),
            profile_path="profiles/x.yaml",
            external_kind_by_module={},  # not declared
        )
    assert kept == (plugin,)
    assert not [w for w in captured if "external-default" in str(w.message)]


def test_modules_not_in_map_treated_as_inprocess() -> None:
    """All-plugins-undeclared-map → no plugin is dropped."""
    plugins = (
        _make_plugin("lca.plugins.a", "lca.plugins.a"),
        _make_plugin("lca.plugins.b", "lca.plugins.b"),
    )
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_external_default_disabled(
            plugins,
            profile_path="profiles/x.yaml",
            external_kind_by_module=None,
        )
    assert kept == plugins
    assert not [w for w in captured if "external-default" in str(w.message)]


def test_filter_does_not_mutate_input_tuple() -> None:
    """The input ``plugins`` tuple is preserved (immutable contract)."""
    plugins = (
        _make_plugin("lca.plugins.a", "lca.plugins.a"),
        _make_plugin("ext.beta", "ext.beta"),
        _make_plugin("lca.plugins.b", "lca.plugins.b"),
    )
    snapshot_ids = tuple(p.id for p in plugins)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        filter_external_default_disabled(
            plugins,
            profile_path="profiles/x.yaml",
            external_kind_by_module={"ext.beta": "mcp"},
        )
    assert tuple(p.id for p in plugins) == snapshot_ids


# ---------------------------------------------------------------------------
# Purity + determinism (C8)
# ---------------------------------------------------------------------------


def test_no_io_side_effects() -> None:
    """The filter module must be pure — no I/O, no env reads, no logging imports.

    Only :mod:`warnings` (stdlib) and the in-package :mod:`external_plugin`
    module are allowed. This mirrors the P3-04 ``test_no_io_side_effects``
    guard pattern.
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
    module_path = repo_root / "lca/harness/profile/resolve/external_filter.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_top_level = {"logging", "subprocess", "socket", "urllib", "requests"}
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module.split(".")[0])

    bad_imports = imported_modules & forbidden_top_level
    assert not bad_imports, f"forbidden imports present: {bad_imports}"

    # The filter must not read environment variables.
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr == "environ"
        ):
            raise AssertionError("filter must not read os.environ")


def test_deterministic_filter_output() -> None:
    """C8 — same input → equal output across repeated calls."""
    plugins = (
        _make_plugin("lca.plugins.a", "lca.plugins.a"),
        _make_plugin("ext.alpha", "ext.alpha"),
        _make_plugin("lca.plugins.b", "lca.plugins.b"),
        _make_plugin("ext.beta", "ext.beta"),
    )
    kinds = {"ext.alpha": "mcp", "ext.beta": "worker"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        first = filter_external_default_disabled(
            plugins, profile_path="profiles/x.yaml", external_kind_by_module=kinds
        )
        second = filter_external_default_disabled(
            plugins, profile_path="profiles/x.yaml", external_kind_by_module=kinds
        )
        third = filter_external_default_disabled(
            plugins, profile_path="profiles/x.yaml", external_kind_by_module=kinds
        )
    assert first == second == third


# ---------------------------------------------------------------------------
# ExternalFilterError export
# ---------------------------------------------------------------------------


def test_external_filter_error_is_value_error() -> None:
    """``ExternalFilterError`` is a ``ValueError`` subclass and importable."""
    assert issubclass(ExternalFilterError, ValueError)
    assert callable(ExternalFilterError)
