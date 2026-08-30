"""Compatibility setup seam for the legacy ``RunRegistry`` path.

Session construction, registry publication, and plugin diagnostics are kept as
separate responsibilities. This module only coordinates their order so the
execution lifecycle receives a coherent, already-published ``RunSession``.
"""

from __future__ import annotations

from typing import Any

from gateway.runs.observability_binding import assemble_run_hub, ensure_session_hub
from gateway.runs.session import RunRegistry, RunSession
from gateway.runs.session_builder import RunSessionBuilder
from gateway.runs.session_diagnostics import (
    RunBootSnapshotRecorder,
    plugin_inventory_from_boot_products,
)
from gateway.runs.session_setup_types import RunSessionRequest


class RunSessionFactory:
    """Coordinate session construction, publication, and creation diagnostics."""

    def __init__(self, registry: RunRegistry | None, *, ctx: Any) -> None:
        if registry is None:
            raise RuntimeError("RunSessionFactory requires a RunRegistry")
        self._registry = registry
        self._builder = RunSessionBuilder(registry, ctx=ctx)
        self._snapshot_recorder = RunBootSnapshotRecorder(ctx=ctx)

    def create(self, request: RunSessionRequest) -> RunSession:
        """Build, publish, and diagnose one legacy run session in that order."""
        session = self._builder.build(request)
        hub = session.hub
        if hub is None:
            raise RuntimeError("RunSessionBuilder must return a session with an observability hub")
        self._registry.put(session)
        self._snapshot_recorder.record(session)
        return session


__all__ = [
    "RunSessionFactory",
    "RunSessionRequest",
    "assemble_run_hub",
    "ensure_session_hub",
    "plugin_inventory_from_boot_products",
]
