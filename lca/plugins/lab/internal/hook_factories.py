"""Lab hook plugin factories (self-contained, no agent_lab dependency).

These replace the agent_lab.plugins.* classes that were deleted in
PR-D final cleanup. Each factory returns a `GraphPlugin` subclass
(from lca.plugins.lab.internal.hooks) that implements the hook
methods the runner dispatches. The classes are minimal stubs — the
real hook logic (event routing, observer dispatch, etc.) is now
delegated to the LCA plugin system.

delete-when (PR-D final 2/2 acceptance):
- This module is only used in test environments. In a real LCA
  runtime with cordis, the hook dispatch goes through the LCA
  provider/plugin system directly and these stubs are unused.
- The 8 lca/plugins/lab/<hook>/plugin.py files import this module
  to create the marker instances; once LCA provides the real hook
  carriers, those imports are replaced.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from lca.plugins.lab.internal.hooks import HookContext, GraphPlugin

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EventSinkPlugin — sinks every event into the lab hook fanout
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EventSinkPlugin(GraphPlugin):
    """Sink every event into the lab hook fanout (default behaviour)."""

    name: str = "default_event_sink"
    kind: str = "event_sink"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def on_event(self, ctx: HookContext) -> HookContext:
        _log.debug("event_sink: %s", ctx.event.value)
        return ctx


# ---------------------------------------------------------------------------
# ObserverPlugin — captures per-event metrics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObserverPlugin(GraphPlugin):
    """Per-event observer: count by event kind + tail for the last N events."""

    name: str = "default_observer"
    kind: str = "observer"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def on_event(self, ctx: HookContext) -> HookContext:
        _log.debug("observer: %s", ctx.event.value)
        return ctx


# ---------------------------------------------------------------------------
# ParseDecisionPlugin — converts raw LLMResponse to a Decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParseDecisionPlugin(GraphPlugin):
    """Convert raw LLMResponse to a Decision artifact.

    In the prototype, the actual parsing logic is delegated to the
    act.think.classify node. This hook only marks the event.
    """

    name: str = "default_parse_decision"
    kind: str = "parse_decision"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def on_decision(self, ctx: HookContext) -> HookContext:
        _log.debug("parse_decision: %s", ctx.event.value)
        return ctx


# ---------------------------------------------------------------------------
# SemanticRouterPlugin — routes outputs by predicate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticRouterPlugin(GraphPlugin):
    """Route outputs by predicate; the control/ route_on node does the
    actual routing logic. This hook only marks the event."""

    name: str = "default_semantic_router"
    kind: str = "semantic_router"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def on_event(self, ctx: HookContext) -> HookContext:
        _log.debug("semantic_router: %s", ctx.event.value)
        return ctx


# ---------------------------------------------------------------------------
# ControlSlotsPlugin — marks the control-slot event family
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ControlSlotsPlugin(GraphPlugin):
    """Mark control-slot events (barrier / join / discard / etc.)."""

    name: str = "default_control_slots"
    kind: str = "control_slots"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def on_event(self, ctx: HookContext) -> HookContext:
        _log.debug("control_slots: %s", ctx.event.value)
        return ctx


# ---------------------------------------------------------------------------
# ObservationRenderPlugin — renders Observation into model-visible text
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObservationRenderPlugin(GraphPlugin):
    """Render Observation into model-visible text.

    The actual rendering is in the reflect/join node. This hook marks
    the event so observers can see when observations become visible.
    """

    name: str = "default_observation_render"
    kind: str = "observation_render"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def on_observation(self, ctx: HookContext) -> HookContext:
        _log.debug("observation_render: %s", ctx.event.value)
        return ctx


# ---------------------------------------------------------------------------
# MemoryExtractPlugin — extract a remember fact
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryExtractPlugin(GraphPlugin):
    """Mark memory-extraction events (the actual work is in remember/extract)."""

    name: str = "default_memory_extract"
    kind: str = "memory_extract"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def on_reflection(self, ctx: HookContext) -> HookContext:
        _log.debug("memory_extract: %s", ctx.event.value)
        return ctx


# ---------------------------------------------------------------------------
# ToolDispatchGuardPlugin — tool dispatch guard
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolDispatchGuardPlugin(GraphPlugin):
    """Mark tool-dispatch events (the actual guard is in tool/grant_check)."""

    name: str = "default_tool_dispatch_guard"
    kind: str = "tool_dispatch_guard"
    binds: tuple = ()
    config: dict = field(default_factory=dict)

    def on_event(self, ctx: HookContext) -> HookContext:
        _log.debug("tool_dispatch_guard: %s", ctx.event.value)
        return ctx


__all__ = [
    "EventSinkPlugin",
    "ObserverPlugin",
    "ParseDecisionPlugin",
    "SemanticRouterPlugin",
    "ControlSlotsPlugin",
    "ObservationRenderPlugin",
    "MemoryExtractPlugin",
    "ToolDispatchGuardPlugin",
]