"""Convergence policy plugin shape test (ADR-0196)."""

from __future__ import annotations

import pytest

from lca.cognition.convergence.runtime import ConvergenceRuntime
from lca.contracts.atoms.scope.scope import Scope
from lca.plugins.cognitive.convergence.policy.plugin import Config, setup


def test_plugin_declares_convergence_capabilities() -> None:
    defn = setup._lca_definition
    from lca.nodes.concept.effect.execute import setup as effect_setup

    assert "convergence_policy" in defn.provided_capability_keys
    assert "convergence_runtime" in defn.provided_capability_keys
    assert "source_registry" in defn.provided_capability_keys
    assert defn.contract.lifecycle.allowed_scopes == (Scope.RUN,)
    assert "source_registry" in effect_setup._lca_definition.required_capability_keys


def test_runtime_default_uses_default_policy() -> None:
    runtime = ConvergenceRuntime.default()
    assert runtime.policy is not None


@pytest.mark.asyncio
async def test_plugin_shares_registry_capability_with_convergence_runtime() -> None:
    class _Context:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        def provide(self, key: object, value: object, **kwargs: object) -> None:
            del kwargs
            self.values[str(key)] = value

    context = _Context()
    await setup.setup(context, Config())  # type: ignore[arg-type]

    registry = context.values["source_registry"]
    runtime = context.values["convergence_runtime"]
    assert isinstance(runtime, ConvergenceRuntime)
    assert runtime.source_registry is registry
