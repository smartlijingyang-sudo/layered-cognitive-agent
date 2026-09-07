"""L1 input contract for the runtime facade.

`RunIntent` is the canonical, surface-agnostic description of a run request.
Every entry point (CLI, HTTP, gateway, test, batch) must construct a
`RunIntent`; the L1 `RuntimeFacade` is the only public consumer that
turns an intent into a `SessionActivation`.

Defined in ADR-0199 §2.2.1. Lives in the ``contracts`` layer: pure data,
no I/O, no env reads, no live ``ctx`` references, no imports from
``lca.harness``, ``lca.application`` or ``lca.plugins``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from lca.contracts.models.core.conversation.conversation import ConversationTurn

RunMode = Literal["solo", "team"]
"""Run coordination mode (ADR-0199 §2.2.1: ``solo | team | ...``)."""

RunSurface = Literal["cli", "http", "gateway", "test", "batch"]
"""Entry surface that produced the intent (ADR-0199 §2.2.1)."""


@dataclass(frozen=True, slots=True)
class RunIntent:
    """Surface-agnostic, immutable description of a run request.

    L0 adapters translate wire formats (HTTP, CLI argv, gateway events,
    batch jobs, tests) into ``RunIntent`` values. L1 ``RuntimeFacade``
    consumes them. The intent carries no live ``ctx`` objects: every
    field is plain data so the value is hashable, replayable and safe
    to log under C8 determinism.
    """

    profile_path: str
    user_text: str
    mode: RunMode
    session_id: str | None
    assistant_id: str | None
    attachment_ids: tuple[str, ...]
    prior_turns: tuple[ConversationTurn, ...]
    execution_target: str
    options: Mapping[str, Any]
    surface: RunSurface
    device_id: str = ""

    def __post_init__(self) -> None:
        if not self.profile_path:
            raise ValueError("RunIntent.profile_path must be non-empty")
        if not self.user_text:
            raise ValueError("RunIntent.user_text must be non-empty")


__all__ = ["RunIntent", "RunMode", "RunSurface"]
