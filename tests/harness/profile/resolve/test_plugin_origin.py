"""Behavioral tests for ``lca.harness.profile.resolve.plugin_origin``.

Covers ``resolve_plugin_origin`` and ``is_untrusted_default_disabled``
per ADR-0199 §3.4 + I-HPC-11 (trust default denied).
"""

from __future__ import annotations

import ast
from pathlib import Path

from lca.contracts.runtime.trust import PluginOrigin
from lca.harness.profile.resolve.plugin_origin import (
    is_untrusted_default_disabled,
    resolve_plugin_origin,
)

# ---------------------------------------------------------------------------
# Bundled plugin classification
# ---------------------------------------------------------------------------


def test_bundled_module_resolves_to_core_origin() -> None:
    """A dotted module path under ``lca.plugins`` → bundled / core."""
    origin = resolve_plugin_origin("lca.plugins.observability.x")
    assert origin.source == "bundled"
    assert origin.trust == "core"


def test_bundled_path_with_slashes_resolves_to_core_origin() -> None:
    """A path-like string under ``lca/plugins/`` also → bundled / core."""
    origin = resolve_plugin_origin("lca/plugins/observability/x.py")
    assert origin.source == "bundled"
    assert origin.trust == "core"


# ---------------------------------------------------------------------------
# Project plugin classification
# ---------------------------------------------------------------------------


def test_project_module_under_dot_lca_resolves_to_untrusted() -> None:
    """A path containing ``.lca/plugins/`` → project / untrusted."""
    origin = resolve_plugin_origin(".lca/plugins/my_team/custom_plugin.py")
    assert origin.source == "project"
    assert origin.trust == "untrusted"


def test_project_path_with_slashes_resolves_to_untrusted() -> None:
    """A path starting with ``.lca/plugins/`` → project / untrusted."""
    origin = resolve_plugin_origin(".lca/plugins/other/thing.py")
    assert origin.source == "project"
    assert origin.trust == "untrusted"


# ---------------------------------------------------------------------------
# Pip entry-point override
# ---------------------------------------------------------------------------


def test_pip_entry_point_overrides_to_pip_untrusted() -> None:
    """``entry_point_group`` forces pip / untrusted regardless of path."""
    origin = resolve_plugin_origin(
        "lca.plugins.something",
        entry_point_group="lca.plugins",
    )
    assert origin.source == "pip"
    assert origin.trust == "untrusted"


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------


def test_unknown_module_falls_back_to_bundled_core() -> None:
    """Unknown module path → bundled / core (safe default)."""
    origin = resolve_plugin_origin("some.random.module.that.does.not.match")
    assert origin.source == "bundled"
    assert origin.trust == "core"


# ---------------------------------------------------------------------------
# Field-level structural assertions
# ---------------------------------------------------------------------------


def test_bundled_origin_has_source_bundled() -> None:
    origin = resolve_plugin_origin("lca.plugins.x")
    assert origin.source == "bundled"


def test_bundled_origin_has_trust_core() -> None:
    origin = resolve_plugin_origin("lca.plugins.x")
    assert origin.trust == "core"


def test_project_origin_has_source_project() -> None:
    origin = resolve_plugin_origin(".lca/plugins/x.py")
    assert origin.source == "project"


def test_project_origin_has_trust_untrusted() -> None:
    origin = resolve_plugin_origin(".lca/plugins/x.py")
    assert origin.trust == "untrusted"


def test_pip_origin_has_source_pip() -> None:
    origin = resolve_plugin_origin("some_module", entry_point_group="lca.plugins")
    assert origin.source == "pip"


def test_pip_origin_has_trust_untrusted() -> None:
    origin = resolve_plugin_origin("some_module", entry_point_group="lca.plugins")
    assert origin.trust == "untrusted"


def test_discovery_at_is_module_path() -> None:
    """``discovered_at`` records the raw module_path the caller passed in."""
    origin = resolve_plugin_origin("lca.plugins.observability.x")
    assert origin.discovered_at == "lca.plugins.observability.x"


def test_enabled_by_mentions_bundled_default_for_bundled() -> None:
    """Bundled plugins carry ``bundled_default`` provenance marker."""
    origin = resolve_plugin_origin("lca.plugins.x")
    assert "bundled_default" in origin.enabled_by


def test_enabled_by_mentions_profile_required_for_project() -> None:
    """Project plugins require explicit profile enable (ADR-0199 §3.4)."""
    origin = resolve_plugin_origin(".lca/plugins/x.py")
    assert "profile_required" in origin.enabled_by


def test_enabled_by_mentions_entry_point_for_pip() -> None:
    """Pip origin records the entry-point group name."""
    origin = resolve_plugin_origin("some_module", entry_point_group="lca.plugins")
    assert "entry_point" in origin.enabled_by
    assert "lca.plugins" in origin.enabled_by


# ---------------------------------------------------------------------------
# is_untrusted_default_disabled (I-HPC-11)
# ---------------------------------------------------------------------------


def test_untrusted_default_disabled_true_for_project() -> None:
    """Project origins are default-disabled (I-HPC-11)."""
    origin = resolve_plugin_origin(".lca/plugins/x.py")
    assert is_untrusted_default_disabled(origin) is True


def test_untrusted_default_disabled_true_for_pip() -> None:
    """Pip origins are default-disabled (I-HPC-11)."""
    origin = resolve_plugin_origin("any", entry_point_group="lca.plugins")
    assert is_untrusted_default_disabled(origin) is True


def test_untrusted_default_disabled_false_for_bundled() -> None:
    """Bundled origins are NOT default-disabled (kernel-shipped)."""
    origin = resolve_plugin_origin("lca.plugins.x")
    assert is_untrusted_default_disabled(origin) is False


def test_untrusted_default_disabled_false_for_user() -> None:
    """User origins are NOT default-disabled (operator-vetted)."""
    home = str(Path.home())
    user_path = f"{home}/.local/share/lca_plugins/custom.py"
    origin = resolve_plugin_origin(user_path)
    assert is_untrusted_default_disabled(origin) is False


# ---------------------------------------------------------------------------
# Module-level invariants: purity + determinism
# ---------------------------------------------------------------------------


def test_no_io_imports_in_module() -> None:
    """The module must be a pure function — no I/O / env reads / logging.

    Only ``pathlib.Path`` is allowed (for the user-home heuristic). I/O modules
    such as ``open()`` calls, ``logging``, ``os.environ``, ``subprocess`` are
    forbidden per the architectural rules (C8 + I-HPC-7 doctor is read-only).
    """
    # Test file lives at tests/harness/profile/resolve/; repo root is parents[4].
    repo_root = Path(__file__).resolve().parents[4]
    module_path = repo_root / "lca/harness/profile/resolve/plugin_origin.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_top_level = {"logging", "subprocess", "socket", "urllib", "requests"}
    forbidden_calls = {"open"}

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module.split(".")[0])

    bad_imports = imported_modules & forbidden_top_level
    assert not bad_imports, f"forbidden imports present: {bad_imports}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden_calls:
                raise AssertionError(f"forbidden I/O call: {func.id}")
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and func.attr == "environ"
            ):
                raise AssertionError("os.environ reads are forbidden in this module")


def test_resolution_deterministic() -> None:
    """C8 — same input must produce equal output across repeated calls."""
    inputs = [
        ("lca.plugins.x",),
        (".lca/plugins/x.py",),
        ("lca/plugins/observability/x.py",),
    ]
    for (path,) in inputs:
        a = resolve_plugin_origin(path)
        b = resolve_plugin_origin(path)
        c = resolve_plugin_origin(path)
        assert a == b == c, f"non-deterministic for {path!r}: {a!r} {b!r} {c!r}"
        # PluginOrigin is frozen + slots: hash is stable
        assert hash(a) == hash(b) == hash(c)


# ---------------------------------------------------------------------------
# Return-type contract: PluginOrigin instance
# ---------------------------------------------------------------------------


def test_returns_plugin_origin_instance() -> None:
    """The function must return a ``PluginOrigin`` dataclass instance."""
    origin = resolve_plugin_origin("lca.plugins.x")
    assert isinstance(origin, PluginOrigin)
