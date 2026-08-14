"""Tool manifest contract — declarative tool identity + API surface (ADR-0015).

Aligns with LobeHub ``BuiltinToolManifest``: a frozen data description of
what a tool offers, with no execution behavior.  Executors interpret the
manifest at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolApi:
    """One callable API exposed by a tool manifest."""

    name: str
    description: str
    parameters: dict[str, Any]
    is_idempotent: bool = False
    default_timeout_ms: int = 30_000


@dataclass(frozen=True)
class ToolMeta:
    """Display metadata for a tool manifest."""

    avatar: str = ""
    title: str = ""
    description: str = ""


@dataclass(frozen=True)
class ToolManifest:
    """Declarative tool identity + API surface.  Pure data — no behavior."""

    identifier: str
    type: str  # "builtin"
    api: tuple[ToolApi, ...]
    executors: tuple[str, ...] = ("server",)
    meta: ToolMeta = field(default_factory=ToolMeta)
    system_role: str = ""
