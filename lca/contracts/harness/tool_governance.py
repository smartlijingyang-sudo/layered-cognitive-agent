"""Optional governance metadata for tools exposed to an autonomous Agent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    INTERNAL_WRITE = "internal_write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ToolGovernance:
    """Declarative policy metadata kept separate from execution behavior."""

    risk: ToolRisk = ToolRisk.READ_ONLY
    side_effect: bool = False
    required_scopes: tuple[str, ...] = ()
    idempotency_required: bool = False
    compensation_tool: str | None = None

    def __post_init__(self) -> None:
        if self.side_effect and self.risk is ToolRisk.READ_ONLY:
            raise ValueError("read-only tools cannot declare side effects")
        if self.idempotency_required and not self.side_effect:
            raise ValueError("idempotency is only required for side effects")
        if self.risk is ToolRisk.DESTRUCTIVE and not self.side_effect:
            raise ValueError("destructive tools must declare side effects")
        if any(not scope.strip() for scope in self.required_scopes):
            raise ValueError("required scopes must not be empty")


@runtime_checkable
class GovernedTool(Protocol):
    """Optional structural seam implemented by tools with governance metadata."""

    governance: ToolGovernance


def is_read_only(governance: ToolGovernance) -> bool:
    """Return whether a tool is safe for a read-only execution profile."""

    return governance.risk is ToolRisk.READ_ONLY and not governance.side_effect


def requires_approval(governance: ToolGovernance) -> bool:
    """Return whether a tool must pause for an explicit human decision."""

    return governance.risk in {
        ToolRisk.INTERNAL_WRITE,
        ToolRisk.EXTERNAL_SIDE_EFFECT,
        ToolRisk.DESTRUCTIVE,
    }


def governance_for(tool: object) -> ToolGovernance:
    """Read optional metadata while keeping legacy tools safely read-only."""

    governance = getattr(tool, "governance", None)
    if governance is None:
        return ToolGovernance()
    if not isinstance(governance, ToolGovernance):
        raise TypeError("tool governance must be a ToolGovernance instance")
    return governance


__all__ = [
    "GovernedTool",
    "ToolGovernance",
    "ToolRisk",
    "governance_for",
    "is_read_only",
    "requires_approval",
]
