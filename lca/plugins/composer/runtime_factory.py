"""Compatibility facade for the standard cognitive runtime factories.

Immutable production bindings and fixture-only defaults live in focused modules.
This facade retains the established public imports while the production assembly
selects its complete Agent Loop through the profile-provided RuntimeFactory.
"""

from __future__ import annotations

from lca.runtime.runtime_loop import CognitiveRuntime
from lca.plugins.composer.fixture_runtime_factory import (
    NullPerceiveHub,
    RuntimeDeps,
    build_fixture_cognitive_runtime,
)
from lca.plugins.composer.internal.runtime_binding import build_production_runtime_bindings
from lca.plugins.composer.internal.runtime_deps import ProductionRuntimeDeps


def build_cognitive_runtime(deps: ProductionRuntimeDeps) -> CognitiveRuntime:
    """Build the default cognitive loop for explicit compatibility callers."""

    return CognitiveRuntime(build_production_runtime_bindings(deps))


__all__ = [
    "NullPerceiveHub",
    "ProductionRuntimeDeps",
    "RuntimeDeps",
    "build_cognitive_runtime",
    "build_fixture_cognitive_runtime",
    "build_production_runtime_bindings",
]
