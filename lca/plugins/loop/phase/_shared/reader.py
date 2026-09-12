"""MappingReader — adapt a plain dict to the PhaseCapabilityReader Protocol.

The subgraph host plugins hand a plain dict (the kernel's
``NodeContext.runtime``) to the standard phase executor's
:func:`StandardPhaseCapabilities` adapter. The adapter expects the
``PhaseCapabilityReader`` Protocol, which requires ``get(name) -> Any``.
This module provides that adapter.
"""

from __future__ import annotations

from typing import Any, Mapping

from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseCapabilityReader,
)


class _MappingReader(PhaseCapabilityReader):
    """Read capability values from a plain mapping.

    Unknown names return ``None`` so the standard phase executor's
    soft-fail paths stay intact (the same behaviour the legacy
    runtime relied on).
    """

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_values", dict(values))

    def get(self, name: str) -> Any:
        return self._values.get(name)


__all__ = ["_MappingReader"]
