"""Regression tests for profile-selected Agent Loop runtime factories."""

from __future__ import annotations

import inspect

import pytest

from lca.contracts.protocols.runtime.runtime_composition import RuntimeFactory
from lca.harness.profile.resolve import resolve_profile
from lca.plugins.composer import runtime_assembly
from lca.plugins.providers.journal.runtime_factory import CognitiveRuntimeFactory


def test_cognitive_runtime_factory_implements_declared_protocol() -> None:
    """The default cognitive loop is exposed through the stable factory seam."""

    assert isinstance(CognitiveRuntimeFactory(), RuntimeFactory)


def test_cognitive_runtime_factory_rejects_non_binding_input() -> None:
    """Loop provider must not accept an unverified or ambient dependency object."""

    with pytest.raises(TypeError, match="DeclarativeRuntimeBindings"):
        CognitiveRuntimeFactory().create(object())


def test_web_profile_declares_runtime_factory() -> None:
    """The default runnable profile explicitly selects its complete Agent Loop."""

    resolved = resolve_profile("profiles/web-standard.yaml")
    provided = {
        capability
        for plugin in resolved.plugins
        for capability in plugin.definition.provided_capability_keys
    }

    assert "runtime_factory" in provided


def test_runtime_assembly_invokes_profile_selected_factory() -> None:
    """L3/L4 assembly may close bindings but cannot select a concrete runtime class."""

    source = inspect.getsource(runtime_assembly)

    assert "build_cognitive_runtime" not in source
    assert "factory.create(bindings)" in source
