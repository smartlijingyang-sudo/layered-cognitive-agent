"""Waterfall / serial / around middleware execution."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any
from dataclasses import dataclass

import structlog

from lca.contracts.harness.middleware import MiddlewareRegistration
from lca.contracts.harness.plugin import ExtensionPoint

_log = structlog.get_logger("lca.harness.middleware")


@dataclass(frozen=True)
class CognitivePhase:
    """Public phase metadata — name + description only.

    ExtensionPoint (internal storage) carries seam_key + dispatch_mode.
    This is the public taxonomy for plugin authors / docs.
    """

    name: str
    description: str = ""


def to_extension_point(phase: CognitivePhase) -> ExtensionPoint:
    """Convert CognitivePhase → ExtensionPoint for internal storage."""
    return ExtensionPoint(seam_key=phase.name, dispatch_mode="waterfall", description=phase.description)


# Public taxonomy (consumed by docs / plugin manifest authors)
COGNITIVE_PHASES: tuple[CognitivePhase, ...] = (
    CognitivePhase("agent.pre_step", "each step before perceive"),
    CognitivePhase("agent.before_perceive", "before perception"),
    CognitivePhase("agent.after_perceive", "after perception"),
    CognitivePhase("agent.before_think", "before thinking"),
    CognitivePhase("agent.after_think", "after thinking"),
    CognitivePhase("agent.before_act", "before act"),
    CognitivePhase("agent.after_act", "after act"),
    CognitivePhase("agent.before_reflect", "before reflect"),
    CognitivePhase("agent.after_reflect", "after reflect"),
    CognitivePhase("agent.before_turn_end", "before turn end"),
)

# Internal storage (preserves registry.run() seam_key/dispatch_mode usage)
COGNITIVE_POINTS: tuple[ExtensionPoint, ...] = tuple(
    to_extension_point(p) for p in COGNITIVE_PHASES
)
# agent.before_turn_end is "serial" — override the default waterfall
COGNITIVE_POINTS = tuple(
    ExtensionPoint(p.seam_key, "serial", p.description)
    if p.seam_key == "agent.before_turn_end" else p
    for p in COGNITIVE_POINTS
)


class SimplePhaseContext:
    def __init__(self, session_id: str = "", record: Callable[[Any], None] | None = None) -> None:
        self._session_id = session_id
        self._record = record

    @property
    def session_id(self) -> str:
        return self._session_id

    def record(self, event_data: Any) -> None:
        if self._record is not None:
            self._record(event_data)


class InMemoryMiddlewareRegistry:
    def __init__(self) -> None:
        self._points: dict[str, ExtensionPoint] = {}
        self._mw: dict[str, list[tuple[MiddlewareRegistration, Any]]] = {}
        for point in COGNITIVE_POINTS:
            self.register_point(point)

    def register_point(self, point: ExtensionPoint) -> None:
        self._points[point.seam_key] = point
        self._mw.setdefault(point.seam_key, [])

    def register(self, registration: MiddlewareRegistration, middleware: Any) -> None:
        if registration.seam_key not in self._points:
            self.register_point(ExtensionPoint(registration.seam_key))
        bucket = self._mw.setdefault(registration.seam_key, [])
        bucket.append((registration, middleware))
        bucket.sort(key=lambda item: item[0].priority)

    def has_point(self, seam_key: str) -> bool:
        return seam_key in self._points

    def list_registrations(self, seam_key: str) -> list[MiddlewareRegistration]:
        return [reg for reg, _ in self._mw.get(seam_key, ())]

    async def run(self, seam_key: str, phase: str, state: Any, context: Any) -> Any:
        point = self._points.get(seam_key)
        mode = point.dispatch_mode if point is not None else "waterfall"
        chain = list(self._mw.get(seam_key, ()))
        if not chain:
            return state
        if mode == "serial":
            for registration, middleware in chain:
                await _invoke(middleware, phase, state, context, registration)
            return state
        if mode == "around":
            return await _run_around(chain, phase, state, context)
        current = state
        for registration, middleware in chain:
            result = await _invoke(middleware, phase, current, context, registration)
            if result is not None:
                current = result
        return current


async def _invoke(
    middleware: Any,
    phase: str,
    state: Any,
    context: Any,
    registration: MiddlewareRegistration,
) -> Any:
    try:
        result = middleware(phase, state, context)
        if inspect.isawaitable(result):
            result = await result
        return result
    except Exception:
        _log.error(
            "middleware_error",
            seam_key=registration.seam_key,
            plugin=registration.plugin_id,
        )
        return state


async def _run_around(
    chain: list[tuple[MiddlewareRegistration, Any]],
    phase: str,
    state: Any,
    context: Any,
) -> Any:
    async def terminal() -> Any:
        return state

    nxt: Callable[[], Awaitable[Any]] = terminal
    for registration, middleware in reversed(chain):

        async def wrapped(
            inner: Callable[[], Awaitable[Any]] = nxt,
            mw: Any = middleware,
            reg: MiddlewareRegistration = registration,
        ) -> Any:
            result = await _invoke(mw, phase, await inner(), context, reg)
            return result if result is not None else state

        nxt = wrapped
    return await nxt()
