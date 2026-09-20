"""Product-environment identity — pure data, no behavior (ADR-0015)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PlaneKind(str, Enum):
    MACHINE = "machine"
    SANDBOX = "sandbox"
    POOL_WORKER = "pool_worker"  # ADR-0246 M1


@dataclass(frozen=True)
class PlaneRef:
    id: str
    label: str
    kind: PlaneKind
    root: str
    outputs_dir: str
    platform: str = ""
    home: str = ""
    capability_summary: tuple[str, ...] = field(default_factory=tuple)  # ADR-0246 M1


@dataclass(frozen=True)
class PlaneBindings:
    primary: PlaneRef | None
    secondary: PlaneRef | None = None
