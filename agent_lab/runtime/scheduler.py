"""Scheduler — topological layers + ready-set computation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Schedule:
    layers: tuple[tuple[str, ...], ...]
    bindings: tuple[dict, ...]

    @property
    def total_nodes(self) -> int:
        return sum(len(layer) for layer in self.layers)
