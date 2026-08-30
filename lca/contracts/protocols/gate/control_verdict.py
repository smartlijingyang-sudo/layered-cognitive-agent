"""Typed control verdict contract shared by the harness and runtime.

The verdict vocabulary is a protocol-level fact.  Keeping it in ``contracts``
prevents the generic declarative interpreter from importing the layer-2 control
aggregator and lets control plugins depend only on the data contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ControlVerdictKind(str, Enum):
    """Closed verdict vocabulary shared by control contributions."""

    ALLOW = "allow"
    DENY = "deny"
    EXHAUSTED = "exhausted"
    STOP = "stop"
    ASK_HUMAN = "ask_human"
    REWRITE = "rewrite"


@dataclass(frozen=True, slots=True)
class ControlVerdict:
    """One active contribution's typed control result."""

    plugin_id: str
    kind: ControlVerdictKind
    detail: str = ""


__all__ = ["ControlVerdict", "ControlVerdictKind"]
