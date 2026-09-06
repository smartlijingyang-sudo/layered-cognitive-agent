"""Contracts for the profile-selected run-mode registry seam.

The gateway and mode-provider plugins share this module rather than importing a
protocol from a concrete plugin.  A mode adapter stays intentionally agnostic
about the gateway request shape, while the registry retains a precise and
substitutable interface for registration, resolution, and inspection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class ModeAdapter(Protocol):
    """Contract for one profile-selectable runtime mode.

    The adapter owns model matching and runnable construction.  ``request``
    deliberately remains ``object`` because this cross-layer seam must not
    import gateway-specific request types.
    """

    @property
    def key(self) -> str: ...

    @property
    def role(self) -> str: ...

    def matches(self, model: str) -> bool: ...

    async def build(self, request: object) -> object: ...


@dataclass(frozen=True, slots=True)
class RegisteredMode:
    """Immutable inspection snapshot for one registered mode adapter."""

    key: str
    role: str
    adapter: ModeAdapter


@runtime_checkable
class RunModeRegistryProtocol(Protocol):
    """Registry seam consumed by gateway mode resolution."""

    def register(self, adapter: ModeAdapter) -> None: ...

    def set_default(self, key: str) -> None: ...

    def resolve(self, model: str) -> ModeAdapter: ...

    def registered(self) -> Sequence[RegisteredMode]: ...

    def __contains__(self, key: str) -> bool: ...


__all__ = ["ModeAdapter", "RegisteredMode", "RunModeRegistryProtocol"]
