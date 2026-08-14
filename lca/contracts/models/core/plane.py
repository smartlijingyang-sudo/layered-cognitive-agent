"""Product-environment identity — pure data, no behavior (ADR-0015)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PlaneKind(str, Enum):
    MACHINE = "machine"
    SANDBOX = "sandbox"


@dataclass(frozen=True)
class PlaneRef:
    id: str
    label: str
    kind: PlaneKind
    root: str
    outputs_dir: str
    platform: str = ""
    home: str = ""


@dataclass(frozen=True)
class PlaneBindings:
    primary: PlaneRef | None
    secondary: PlaneRef | None = None
