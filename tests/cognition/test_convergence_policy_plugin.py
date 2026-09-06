"""Convergence policy plugin shape test (ADR-0196)."""

from __future__ import annotations

from lca.cognition.convergence.runtime import ConvergenceRuntime
from lca.plugins.cognitive.convergence.policy.plugin import setup


def test_plugin_declares_convergence_capabilities() -> None:
    defn = setup._lca_definition
    assert "convergence_policy" in defn.provided_capability_keys
    assert "convergence_runtime" in defn.provided_capability_keys


def test_runtime_default_uses_default_policy() -> None:
    runtime = ConvergenceRuntime.default()
    assert runtime.policy is not None
