"""Perception contracts — ContextItem, ContextManifest, PerceptionMerged (PR2).

The Hub emits a single ``ContextManifested`` event per turn carrying the
complete ``ContextManifest`` (a curated list of ``ContextItem`` objects).
Each item is a tagged ``(kind, payload, ref, provenance)`` atom.  The
Reasoner consumes the manifest — never a live workspace read.

Item kinds (closed set, allowlist):

- ``clock`` — current date/time snapshot (clock sensor)
- ``workspace_artifacts`` — registered artifact list (workspace sensor)
- ``workspace_instructions`` — AGENTS.md / system files (PR13)
- ``skill_catalog`` — installed skill list (PR14)
- ``inbox_facts`` — recent inbox items (PR8)
- ``team_inbox`` — team message inbox (PR9)
- ``policy_fact`` — derived from a GateDecided event (PR4)
- ``memory`` — MemoryRecord curated from Memory.perceive (PR3a)
- ``subtasks`` — derived from prior turns (PR3c)

New kinds must be added here and to the EmitAllowlist in tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal

# Closed allowlist of ContextItem kinds.  Additions must be intentional.
ItemKind = Literal[
    "clock",
    "workspace_artifacts",
    "workspace_instructions",
    "skill_catalog",
    "inbox_facts",
    "team_inbox",
    "policy_fact",
    "memory",
    "subtasks",
]


# Single pairing point for kind->payload-type knowledge: each closed-set
# kind maps to the tuple of acceptable Python payload shapes.  A new kind
# pairs exactly one ItemKind member with exactly one entry here.
#
# This records the *consumer contract* (the shape the reasoner side
# expects).  Producers that historically emit a different shape for a kind
# (e.g. assistant-bootstrap face items with dict payloads under
# "workspace_artifacts") are filtered out by ContextManifest.payload_of —
# the same filtering the cognition helpers did inline before RA-093.
KIND_PAYLOAD_TYPES: Mapping[ItemKind, tuple[type, ...]] = MappingProxyType(
    {
        "clock": (str,),
        "workspace_artifacts": (list,),
        "workspace_instructions": (str,),
        "skill_catalog": (list,),
        "inbox_facts": (list,),
        "team_inbox": (list,),
        "policy_fact": (str,),
        "memory": (list,),
        "subtasks": (list,),
    }
)


class ContextClass(StrEnum):
    DATA = "data"
    INSTRUCTION = "instruction"
    SYSTEM = "system"


@dataclass(frozen=True)
class ContextItem:
    """A single tagged atom in a ContextManifest.

    - ``kind``: one of the closed allowlist (ItemKind)
    - ``payload``: opaque Python value; the per-kind shape contract
      lives in KIND_PAYLOAD_TYPES.  The Portal serializes via JSON.
    - ``ref``: optional pointer to a journal seq or blob ref for the full
      payload (forwarded-only; the spec defaults to ``refs`` + digest only)
    - ``provenance``: who emitted it (sensor name, gate name, etc.)
    - ``extra``: opaque metadata dict
    """

    kind: ItemKind
    payload: Any
    provenance: str
    ref: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    content_class: ContextClass = ContextClass.DATA


@dataclass(frozen=True)
class ContextManifest:
    """A complete, curated manifest for one turn.

    Emitted exactly once per turn by the PerceiveHub (PR3a).  The Reasoner
    is the only consumer: it reads ``items`` and renders the prompt
    strictly from this list, never from a live workspace read.
    """

    items: tuple[ContextItem, ...]
    digest: str = ""
    schema_version: str = "1.0"
    extra: dict[str, Any] = field(default_factory=dict)

    def by_class(self, content_class: ContextClass) -> list[ContextItem]:
        return [item for item in self.items if item.content_class == content_class]

    def by_kind(self, kind: ItemKind) -> list[ContextItem]:
        return [item for item in self.items if item.kind == kind]

    def has_kind(self, kind: ItemKind) -> bool:
        return any(item.kind == kind for item in self.items)

    def payload_of(self, kind: ItemKind) -> list[Any]:
        """Return payloads of ``kind`` items whose payload matches the kind's
        declared shape (see ``KIND_PAYLOAD_TYPES``).

        The manifest itself owns the kind->payload-type knowledge; callers
        no longer repeat per-kind isinstance checks.  Items whose payload
        does not match the declared shape are filtered out (producers may
        emit legacy shapes; consumers only see the contract shape).
        """
        expected = KIND_PAYLOAD_TYPES.get(kind)
        if not expected:
            return []
        return [
            item.payload
            for item in self.items
            if item.kind == kind and isinstance(item.payload, expected)
        ]
