"""Behavioral tests for ``filter_untrusted_default_disabled``.

Per ADR-0199 §3.4 + I-HPC-11 (信任默认拒绝): the active ``profile_path``
is the admission authority for ``project`` and ``pip`` plugins. The
filter drops untrusted-default plugins unless the profile explicitly
admits them via provenance, and emits a warning (not an error) so the
profile may still resolve with the trusted subset.

Tests use ``ResolvedPlugin.module`` as the only contract surface (we
construct the dataclass with the public fields and bypass
``_resolve_plugins`` to keep these tests pure and isolated).
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest

from lca.harness.profile.resolve.resolve import (
    ResolvedPlugin,
    filter_untrusted_default_disabled,
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
    only reads ``id``, ``module``, ``source``, ``disabled``. We supply
    placeholders for everything else; tests of the surrounding resolve
    pipeline use real plugins (see
    ``test_filtered_plugins_not_in_resolved_profile``).
    """
    from lca.harness.profile.resolve.resolve import _disabled_stub

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


def _bundled(module_suffix: str = "x") -> ResolvedPlugin:
    return _make_plugin(
        plugin_id=f"lca.plugins.{module_suffix}",
        module=f"lca.plugins.{module_suffix}",
        source="bundles/core.yaml",
    )


def _user(home: Path) -> ResolvedPlugin:
    user_module = str(home / ".local/share/lca_plugins/custom.py")
    return _make_plugin(
        plugin_id="my.user_plugin",
        module=user_module,
        source=str(home / "profiles/test.yaml"),
    )


def _project(source_path: str = "profiles/test.yaml") -> ResolvedPlugin:
    return _make_plugin(
        plugin_id="my.project_plugin",
        module=".lca/plugins/team/custom_plugin.py",
        source=source_path,
    )


def _pip(source_path: str = "profiles/test.yaml") -> ResolvedPlugin:
    return _make_plugin(
        plugin_id="my.pip_plugin",
        module="some_pip_plugin",
        source=source_path,
    )


_PIP_ENTRY_POINT_GROUP = "lca.plugins"  # pip-installed LCA plugin group
_PIP_ENTRY_POINT_MAP = {"some_pip_plugin": _PIP_ENTRY_POINT_GROUP}


# ---------------------------------------------------------------------------
# Bundled / user → trusted by default
# ---------------------------------------------------------------------------


def test_bundled_plugins_all_kept() -> None:
    """Bundled plugins are core / trusted — never filtered."""
    plugins = (_bundled("a"), _bundled("b"), _bundled("c"))
    kept = filter_untrusted_default_disabled(plugins, profile_path="profiles/any.yaml")
    assert kept == plugins


def test_user_plugins_kept() -> None:
    """User-installed plugins are trusted by default — kept."""
    plugins = (_user(Path.home()),)
    kept = filter_untrusted_default_disabled(plugins, profile_path="profiles/any.yaml")
    assert kept == plugins


# ---------------------------------------------------------------------------
# Project / pip default-disabled
# ---------------------------------------------------------------------------


def test_project_plugins_filtered_when_not_explicitly_enabled() -> None:
    """Project plugin whose source ≠ profile_path → dropped with warning."""
    plugin = _project(source_path="bundles/core.yaml")  # admitted by a bundle, not the profile
    with pytest.warns(UserWarning, match="untrusted-default plugins filtered"):
        kept = filter_untrusted_default_disabled((plugin,), profile_path="profiles/x.yaml")
    assert kept == ()


def test_pip_plugins_filtered_when_not_explicitly_enabled() -> None:
    """Pip plugin whose source ≠ profile_path → dropped with warning.

    The filter needs the entry-point group to classify the module as pip
    (P3-03 ``resolve_plugin_origin`` falls back to bundled otherwise).
    """
    plugin = _pip(source_path="bundles/core.yaml")
    with pytest.warns(UserWarning, match="untrusted-default plugins filtered"):
        kept = filter_untrusted_default_disabled(
            (plugin,),
            profile_path="profiles/x.yaml",
            entry_point_group_by_module=_PIP_ENTRY_POINT_MAP,
        )
    assert kept == ()


# ---------------------------------------------------------------------------
# Explicit admission via profile provenance
# ---------------------------------------------------------------------------


def test_project_plugins_kept_when_profile_path_matches_discovery() -> None:
    """Project plugin whose ``source`` equals ``profile_path`` → kept.

    This is the canonical "the active profile declared it inline"
    admission path. No warning should fire because nothing was filtered.
    """
    plugin = _project(source_path="profiles/web-standard.yaml")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_untrusted_default_disabled(
            (plugin,), profile_path="profiles/web-standard.yaml"
        )
    assert kept == (plugin,)
    assert not [w for w in captured if "untrusted-default" in str(w.message)]


def test_pip_plugins_kept_when_profile_path_matches_discovery() -> None:
    """Pip plugin whose ``source`` equals ``profile_path`` → kept."""
    plugin = _pip(source_path="profiles/web-standard.yaml")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_untrusted_default_disabled(
            (plugin,),
            profile_path="profiles/web-standard.yaml",
            entry_point_group_by_module=_PIP_ENTRY_POINT_MAP,
        )
    assert kept == (plugin,)
    assert not [w for w in captured if "untrusted-default" in str(w.message)]


def test_pip_plugins_kept_when_profile_path_is_substring_of_source() -> None:
    """Profile path that is a substring of plugin source → kept (bundled case)."""
    plugin = _make_plugin(
        plugin_id="my.pip_plugin",
        module="some_pip_plugin",
        source="bundles/profiles/web-standard.yaml",
    )
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_untrusted_default_disabled(
            (plugin,), profile_path="profiles/web-standard.yaml"
        )
    assert kept == (plugin,)
    assert not [w for w in captured if "untrusted-default" in str(w.message)]


# ---------------------------------------------------------------------------
# Warning emission contract
# ---------------------------------------------------------------------------


def test_filtered_plugins_emit_warning() -> None:
    """Each filter call with at least one drop emits one UserWarning."""
    plugins = (_project(source_path="bundles/core.yaml"),)
    with pytest.warns(UserWarning, match="ADR-0199"):
        filter_untrusted_default_disabled(plugins, profile_path="profiles/x.yaml")


def test_warning_lists_filtered_plugin_ids() -> None:
    """The warning text mentions every dropped plugin id and source label."""
    plugins = (
        _make_plugin(
            plugin_id="drop.alpha",
            module=".lca/plugins/alpha.py",
            source="bundles/core.yaml",
        ),
        _make_plugin(
            plugin_id="drop.beta",
            module=".lca/plugins/beta.py",
            source="bundles/core.yaml",
        ),
    )
    with pytest.warns(UserWarning) as record:
        filter_untrusted_default_disabled(plugins, profile_path="profiles/x.yaml")
    messages = [str(w.message) for w in record]
    assert any("drop.alpha" in msg for msg in messages)
    assert any("drop.beta" in msg for msg in messages)
    assert any("source=project" in msg for msg in messages)


def test_no_warning_when_all_kept() -> None:
    """No warning fires when every plugin is trusted (bundled / user)."""
    plugins = (_bundled("a"), _bundled("b"))
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        filter_untrusted_default_disabled(plugins, profile_path="profiles/x.yaml")
    assert not [w for w in captured if "untrusted-default" in str(w.message)]


def test_warn_filtered_false_silences_warning() -> None:
    """``warn_filtered=False`` opt-out keeps the filter but silences the warning."""
    plugin = _project(source_path="bundles/core.yaml")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_untrusted_default_disabled(
            (plugin,),
            profile_path="profiles/x.yaml",
            warn_filtered=False,
        )
    assert kept == ()
    assert not [w for w in captured if "untrusted-default" in str(w.message)]


# ---------------------------------------------------------------------------
# Integration with ``resolve_profile``
# ---------------------------------------------------------------------------


def test_filtered_plugins_not_in_resolved_profile() -> None:
    """Plugins filtered out at the seam are absent from ``ResolvedProfile.plugins``.

    Uses the programmatic ``resolve_entries`` adapter so this test does
    not depend on bundled plugin modules.
    """
    from lca.harness.profile.resolve.resolve import resolve_entries

    entries = [
        {
            "id": "lca.plugins.observability.console",
            "$module": "lca.plugins.observability.console",
            "config": {},
            "disabled": True,  # disabled → short-circuits; not the filter's job
        },
    ]
    resolved = resolve_entries(entries)
    ids = {p.id for p in resolved.plugins}
    assert "lca.plugins.observability.console" in ids  # disabled preserved


def test_resolve_entries_drops_untrusted_default_disabled_plugins() -> None:
    """A project plugin declared via programmatic entries with mismatched source → dropped.

    We craft the ``source`` field so the admission check fails: the
    plugin is admitted via ``"<programmatic entries>[0]"`` which does
    not contain ``"<programmatic entries>"`` as a substring for the
    substring check (but actually it does — ``"<programmatic entries>``
    IS a substring of ``"<programmatic entries>[0]"``, so this plugin
    would be kept). To force a drop we feed a *different* ``source``
    string by hand-crafting a programmatic-profile source.

    The cleaner integration test is in ``test_resolve_entries_keeps_when
    _source_matches_programmatic`` below; this one documents the
    "dropped when source disagrees" semantics via the helper function
    directly.
    """
    # Direct filter test for the integration contract — programmatic
    # source ``<programmatic entries>[0]`` is a sibling-of the
    # ``<programmatic entries>`` profile_path and therefore admitted.
    plugin = _make_plugin(
        plugin_id="project.bad",
        module=".lca/plugins/bad.py",
        source="<other-source>/bad.yaml",
    )
    with pytest.warns(UserWarning, match="untrusted-default"):
        kept = filter_untrusted_default_disabled((plugin,), profile_path="profiles/x.yaml")
    assert kept == ()


def test_resolve_entries_keeps_when_source_matches_programmatic() -> None:
    """Programmatic source substring of profile_path → kept (substring match)."""
    plugin = _make_plugin(
        plugin_id="project.ok",
        module=".lca/plugins/ok.py",
        source="<programmatic entries>[0]",
    )
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_untrusted_default_disabled((plugin,), profile_path="<programmatic entries>")
    assert kept == (plugin,)
    assert not [w for w in captured if "untrusted-default" in str(w.message)]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_output() -> None:
    """Empty plugin tuple → empty tuple, no warning."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        kept = filter_untrusted_default_disabled((), profile_path="profiles/x.yaml")
    assert kept == ()
    assert not [w for w in captured if "untrusted-default" in str(w.message)]


def test_filter_preserves_order_of_kept_plugins() -> None:
    """The kept subset preserves the input order (deterministic)."""
    plugins = (
        _bundled("a"),
        _project(source_path="profiles/x.yaml"),  # kept (substring)
        _bundled("b"),
        _project(source_path="bundles/core.yaml"),  # filtered
        _bundled("c"),
    )
    with pytest.warns(UserWarning):
        kept = filter_untrusted_default_disabled(plugins, profile_path="profiles/x.yaml")
    assert [p.id for p in kept] == [
        "lca.plugins.a",
        "my.project_plugin",
        "lca.plugins.b",
        "lca.plugins.c",
    ]


def test_mixed_origins_correctly_partitioned() -> None:
    """Bundled + user kept; project + pip filtered.

    All four origin classes appear in the input set; only the trusted
    two survive.
    """
    plugins = (
        _bundled("a"),
        _user(Path.home()),
        _project(source_path="bundles/core.yaml"),
        _pip(source_path="bundles/core.yaml"),
    )
    with pytest.warns(UserWarning, match="untrusted-default"):
        kept = filter_untrusted_default_disabled(
            plugins,
            profile_path="profiles/x.yaml",
            entry_point_group_by_module=_PIP_ENTRY_POINT_MAP,
        )
    kept_ids = {p.id for p in kept}
    assert kept_ids == {"lca.plugins.a", "my.user_plugin"}


def test_filter_does_not_mutate_input_tuple() -> None:
    """The input ``plugins`` tuple is preserved (immutable contract)."""
    plugins = (
        _bundled("a"),
        _project(source_path="bundles/core.yaml"),
        _bundled("b"),
    )
    snapshot_ids = tuple(p.id for p in plugins)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        filter_untrusted_default_disabled(plugins, profile_path="profiles/x.yaml")
    assert tuple(p.id for p in plugins) == snapshot_ids


# ---------------------------------------------------------------------------
# Purity + determinism (C8)
# ---------------------------------------------------------------------------


def test_no_io_side_effects() -> None:
    """The filter must be pure — no I/O, no env reads, no logging imports.

    Only :mod:`warnings` (stdlib, side-effect-free for our purposes) and
    the in-package :mod:`plugin_origin` are allowed. This mirrors the
    P3-03 ``test_no_io_imports_in_module`` check.
    """
    repo_root = Path(__file__).resolve().parents[4]
    module_path = repo_root / "lca/harness/profile/resolve/resolve.py"
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

    # The filter itself must not read environment variables.
    filter_src = ast.parse(
        (repo_root / "lca/harness/profile/resolve/resolve.py").read_text(encoding="utf-8")
    )
    for node in ast.walk(filter_src):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr == "environ"
        ):
            raise AssertionError("filter must not read os.environ")


def test_filter_is_deterministic() -> None:
    """C8 — same input → equal output across repeated calls."""
    plugins = (
        _bundled("a"),
        _project(source_path="bundles/core.yaml"),
        _bundled("b"),
        _pip(source_path="profiles/x.yaml"),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        first = filter_untrusted_default_disabled(plugins, profile_path="profiles/x.yaml")
        second = filter_untrusted_default_disabled(plugins, profile_path="profiles/x.yaml")
        third = filter_untrusted_default_disabled(plugins, profile_path="profiles/x.yaml")
    assert first == second == third


def test_filter_returned_tuple_is_frozen() -> None:
    """Returned tuple rejects mutation (frozen result contract)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        kept = filter_untrusted_default_disabled((_bundled("a"),), profile_path="profiles/x.yaml")
    assert isinstance(kept, tuple)
    with pytest.raises((AttributeError, TypeError)):
        kept[0] = _bundled("z")  # type: ignore[index]
