"""EffectMeta — diagnostic tree node for plugin effects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EffectMeta:
    """One node in the effect diagnostic tree."""

    label: str
    children: list[EffectMeta] = field(default_factory=list)
