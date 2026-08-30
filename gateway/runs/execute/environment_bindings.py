"""Resolve explicit runtime bindings for the legacy Gateway carrier.

This module owns capability lookups and plane/driver selection only.  It does not
enter ambient scopes, mutate a ``RunSession``, or perform attachment effects;
those responsibilities stay with the environment coordinator and staging unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import structlog

from gateway.runs.execute.loop_drivers import RunLoopDriver
from gateway.runs.session.intent import resolve_run_intent
from gateway.runs.session.session import RunSession
from lca.contracts.mechanisms.capability import provider_current, require_capability
from lca.contracts.models.core.plane import PlaneBindings, PlaneKind
from lca.contracts.protocols.runtime.infra import MachineResolver, Sandbox
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.plane.resolve import (
    PlaneRequest,
    ref_of,
    resolve_plane_bindings,
    sandbox_ref_from,
)

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RunProviders:
    """Infrastructure providers available to one resolved run environment."""

    sandbox: Sandbox | None
    file_store: FileStore | None


def resolve_bindings(
    session: RunSession,
    ctx: Any,
    machine_resolver: MachineResolver | None,
) -> PlaneBindings:
    """Resolve the requested execution planes from the booted capability tree."""
    sandbox = cast("Sandbox | None", provider_current(require_capability(ctx, "sandbox")))
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    machine = (
        machine_resolver.resolve_machine(session.device_id or None)
        if machine_resolver is not None
        else None
    )
    bindings = resolve_plane_bindings(
        machine,
        sandbox_ref,
        PlaneRequest(
            device_id=session.device_id,
            plane=session.plane,
            extra_plane=session.extra_plane,
            execution_target=session.execution_target,
        ),
    )
    _log_plane_selection(bindings)
    return bindings


def resolve_driver(session: RunSession, ctx: Any) -> RunLoopDriver:
    """Select the profile-registered loop driver for the requested run intent."""
    driver_registry = require_capability(ctx, "run_loop_driver_registry")
    intent = resolve_run_intent(
        driver_registry,
        execution_target=session.execution_target,
        plane=session.plane,
        extra_plane=session.extra_plane,
        device_id=session.device_id,
    )
    return cast("RunLoopDriver", intent.driver)


def resolve_run_providers(bindings: PlaneBindings, ctx: Any) -> RunProviders:
    """Resolve providers that are actually reachable through the selected planes."""
    sandbox = cast("Sandbox | None", provider_current(require_capability(ctx, "sandbox")))
    if sandbox is None or ref_of(bindings, PlaneKind.SANDBOX) is None:
        sandbox = None
    file_store = cast("FileStore | None", provider_current(require_capability(ctx, "file_store")))
    return RunProviders(sandbox=sandbox, file_store=file_store)


def resolve_descriptor_registry(ctx: Any) -> Any:
    """Prefer the profile-bound descriptor registry; use legacy fallback otherwise."""
    registry = ctx.inject("event_descriptor_registry", default=None)
    if registry is not None:
        return registry
    from lca.infrastructure.observability.event_catalog import EVENT_DESCRIPTOR_REGISTRY

    return EVENT_DESCRIPTOR_REGISTRY


def _log_plane_selection(bindings: PlaneBindings) -> None:
    machine = ref_of(bindings, PlaneKind.MACHINE)
    if machine is not None:
        _log.info(
            "plane_bound",
            kind=machine.kind.value,
            plane_id=machine.id,
            root=machine.root,
            role="machine",
        )
    if bindings.primary is not None:
        _log.info(
            "plane_primary",
            kind=bindings.primary.kind.value,
            plane_id=bindings.primary.id,
            root=bindings.primary.root,
        )


__all__ = [
    "RunProviders",
    "resolve_bindings",
    "resolve_descriptor_registry",
    "resolve_driver",
    "resolve_run_providers",
]
