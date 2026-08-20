"""Composition-time gating — post-cordis migration.

Only `consume()` remains. The SeamRole / SeamDeclaration / SeamRegistry /
seam / validate_all_seams machinery was LCA 早期自创; cordis's
@plugin/inject/provide replaces it.

`consume()` is the composition-time gate: it declares a consumer as
officially a CONSUMER of a definition's seam and returns the provider
unchanged. Domain classes (Brain / Reasoner / Runtime) take the provider
via constructor injection; no Service Locator look-ups.
"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


def consume(definition: str, provider: T, consumer: Any) -> T:
    """Composition-time gate. Returns provider unchanged."""
    return provider
