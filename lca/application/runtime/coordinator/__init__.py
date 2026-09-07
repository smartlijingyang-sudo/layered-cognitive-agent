"""LcaAgentRuntimeCoordinator — StampedEvent → Redis stream fold.

Mirror of `apps/server/src/modules/AgentRuntime/AgentRuntimeCoordinator.ts`.
Subscribes to `LiveRunProjection.tail` and publishes AgentStreamEvent
into Redis via LcaStreamEventManager.
"""

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.application.runtime.coordinator.terminal_hints import (
    TerminalHint,
    is_stream_terminal_status,
    resolve_live_terminal_hint,
)

__all__ = (
    "EventTranslator",
    "TerminalHint",
    "is_stream_terminal_status",
    "resolve_live_terminal_hint",
)
