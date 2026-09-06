"""Model-visible request assembly — Session fold → LLM wire (ADR-0191 Wave A1).

Pure Protocol + DTO; no I/O. Runtime implementation lives in
``lca.infrastructure.session.model_context_assembler``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SessionReader(Protocol):
    """Minimal Session read face for model-context fold."""

    def derive_messages(self) -> list[dict[str, Any]]: ...

    def request_header(self) -> object | None:
        """Last folded request header; absent when no header events exist."""
        ...


@dataclass(frozen=True, slots=True)
class ModelVisibleRequest:
    """One LLM round-trip's model-visible slice (messages + optional header)."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    system: str | None = None
    config: dict[str, Any] | None = None
    tools: tuple[dict[str, Any], ...] = field(default_factory=tuple)


class ModelContextAssembler(Protocol):
    """Fold Session facts into the model-visible request for one step."""

    def assemble(self, session: SessionReader, *, step: int) -> ModelVisibleRequest: ...


__all__ = ["ModelContextAssembler", "ModelVisibleRequest", "SessionReader"]
