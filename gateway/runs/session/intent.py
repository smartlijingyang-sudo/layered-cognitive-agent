"""Wire intent: split LobeHub's overloaded ``execution_target`` into loop + plane.

Two orthogonal primitives share one historical wire field:

- **Loop id** — registered on ``run_loop_driver_registry`` (``cognitive``, ``dsh``, …)
- **Plane hint** — ``sandbox`` / ``device`` / ``auto`` / ``none`` (+ aliases)

Gateway is the only place that knows this wire conflation. Downstream code
consumes either a resolved driver or a ``PlaneRequest``, never the raw soup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.infrastructure.plane.execution_target import parse_execution_target
from lca.infrastructure.plane.resolve import PlaneRequest
from lca.plugins.loop_drivers.registry import (
    RunLoopDriverRegistry,
    _UnknownExecutionTargetError,
)


@dataclass(frozen=True)
class RunIntent:
    """Resolved carrier intent for one ``/runs`` execution."""

    driver: Any
    plane: PlaneRequest


def resolve_run_intent(
    registry: RunLoopDriverRegistry,
    *,
    execution_target: str = "",
    plane: str = "",
    extra_plane: str = "",
    device_id: str = "",
) -> RunIntent:
    """Map wire fields → (loop driver, plane request).

    Rules:
    1. Registered loop id → that driver; plane hint comes only from ``plane``.
    2. Empty or parseable plane hint → profile default driver + that hint.
    3. Anything else → unknown (missing loop plugin or garbage token).
    """
    raw = (execution_target or "").strip().lower()
    if registry.contains(raw):
        driver = registry.resolve(raw)
        plane_et = ""
    elif not raw or parse_execution_target(raw) is not None:
        driver = registry.resolve("")
        plane_et = raw
    else:
        raise _UnknownExecutionTargetError(raw)
    return RunIntent(
        driver=driver,
        plane=PlaneRequest(
            device_id=device_id,
            plane=plane,
            extra_plane=extra_plane,
            execution_target=plane_et,
        ),
    )
