"""LcaAgentRuntimeCoordinator — StampedEvent → Redis stream fold.

Mirror of `apps/server/src/modules/AgentRuntime/AgentRuntimeCoordinator.ts`.
Subscribes to `LiveRunProjection.tail` and publishes AgentStreamEvent
into Redis via LcaStreamEventManager.
"""

from lca.application.runtime.coordinator.event_translator import EventTranslator

__all__ = ("EventTranslator",)
