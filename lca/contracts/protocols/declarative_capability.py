"""Native capability declaration contract for declarative plugins.

A capability has two deliberate identities: its architectural key and the
exact key exposed by a booted Cordis scope. Keeping that translation beside the
capability contract gives all plan projections one stable source of resolution
truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.protocols.declarative_common import (
    CARDINALITIES,
    DeclarativeValidationError,
)


def _as_text_tuple(value: tuple[str, ...] | Any) -> tuple[str, ...]:
    """Normalize declaration text collections while preserving tuple identity."""
    return value if isinstance(value, tuple) else tuple(str(item) for item in value)


@dataclass(frozen=True, slots=True)
class CapabilityDeclaration:
    """One provided or required capability in the native plugin contract.

    ``key`` identifies the architectural capability, while ``resolution_key``
    identifies the exact Cordis key exposed by the booted scope. They differ
    for selector and registry contributions; recording both at declaration time
    keeps plan consumers from re-inferring scope behavior from names.
    """

    key: str
    cardinality: str = "one"
    protocol: str = "object"
    scope: str = "run"
    grant: tuple[str, ...] = ()
    resolution_key: str | None = None

    def __post_init__(self) -> None:
        if not self.key:
            raise DeclarativeValidationError("PS-001", "capability key must be non-empty")
        if self.cardinality not in CARDINALITIES:
            raise DeclarativeValidationError("PS-001", f"invalid cardinality: {self.cardinality}")
        if not self.protocol:
            raise DeclarativeValidationError("PS-001", "capability protocol must be non-empty")
        if self.resolution_key is not None and not self.resolution_key:
            raise DeclarativeValidationError(
                "PS-001", "capability resolution_key must be non-empty when declared"
            )
        object.__setattr__(self, "grant", _as_text_tuple(self.grant))
        if self.resolution_key is None:
            object.__setattr__(self, "resolution_key", self.key)


__all__ = ["CapabilityDeclaration"]
