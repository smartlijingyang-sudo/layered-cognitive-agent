"""Runtime acceptance gate for the Hermes capability surface."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityCheck:
    name: str
    implemented: bool
    detail: str


@dataclass(frozen=True)
class HermesCapabilityGate:
    checks: tuple[CapabilityCheck, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.implemented for check in self.checks)

    def require_passed(self) -> None:
        failed = [check.name for check in self.checks if not check.implemented]
        if failed:
            raise RuntimeError("Hermes capability gate failed: " + ", ".join(failed))


__all__ = ["CapabilityCheck", "HermesCapabilityGate"]
