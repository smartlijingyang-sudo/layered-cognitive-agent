"""Tool manifest contract — declarative tool identity + API surface (ADR-0015).

Aligns with LobeHub ``BuiltinToolManifest``: a frozen data description of
what a tool offers, with no execution behavior.  Executors interpret the
manifest at runtime.

Per ADR-0101 §5.2/§6 each Tool Provider self-describes its parameter
schema via :class:`ParameterSpec` entries on the manifest. The journal
layer never interprets ``ui_hint`` — it is a renderer-dispatch concept
owned by the LobeHub renderer registry (see
``deploy/lobehub/patches/runtime/renderers/index.ts``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParameterSpec:
    """One named parameter declared by a :class:`ToolManifest` (ADR-0101 §5.2).

    ``type`` mirrors the JSON Schema vocabulary (``string`` / ``number`` /
    ``integer`` / ``boolean`` / ``object`` / ``array``). ``required`` and
    ``default`` follow JSON Schema semantics. ``ui_hint`` is the LobeHub
    renderer dispatch keyword (e.g. ``terminal``, ``code``, ``path``,
    ``tree``); absent hint means the renderer registry will use its
    ``JsonRenderer`` fallback for this argument.
    """

    type: str
    required: bool = False
    default: Any = None
    ui_hint: str = ""
    description: str = ""


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
    """Declarative tool identity + API surface. Pure data, no behavior.

    ``parameters`` is the typed tool-level argument map introduced by
    ADR-0101 §5.2: each entry's key is an argument name; the value is a
    :class:`ParameterSpec`. Manifests that predate the ADR default to an
    empty mapping; ``ToolApi.parameters`` keeps the JSON-Schema form used
    by the tool class itself.
    """

    identifier: str
    type: str  # "builtin"
    api: tuple[ToolApi, ...]
    executors: tuple[str, ...] = ("server",)
    meta: ToolMeta = field(default_factory=ToolMeta)
    system_role: str = ""
    parameters: Mapping[str, ParameterSpec] = field(default_factory=dict)


__all__ = ["ParameterSpec", "ToolApi", "ToolManifest", "ToolMeta"]
