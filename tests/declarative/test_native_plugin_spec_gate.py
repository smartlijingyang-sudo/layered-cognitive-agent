"""Fail-closed coverage for native PluginSpec admission to declarative plans."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from lca.harness.declarative.compile.compiler import compile_declarative_projection
from lca.harness.profile.resolve import resolve_profile


def test_declarative_compilation_rejects_an_active_legacy_plugin_definition() -> None:
    """A profile may not infer execution semantics from old decorator fields."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    legacy_plugin = SimpleNamespace(
        id="legacy.untyped",
        definition=SimpleNamespace(spec=None),
        config={},
        disabled=False,
    )
    broken = replace(resolved, plugins=(legacy_plugin,))

    with pytest.raises(ValueError, match=r"PS-002.*native PluginSpec"):
        compile_declarative_projection(broken)
