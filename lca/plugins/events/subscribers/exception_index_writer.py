"""ExceptionIndexWriter — Session observer for ``exception.caught`` index (ADR-0183).

Filters ``exception.caught`` from the Session observer stream and enqueues
lines into the per-run exceptions write-behind buffer (``*.exceptions.jsonl``).
Does not perform direct disk I/O; shares :class:`RunWriteBehindRegistry` with
:class:`PersistenceObserver`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.persistence.run_buffer_registry import RunWriteBehindRegistry
from lca.infrastructure.persistence.run_paths import run_id_from_event_id
from lca_kernel.events.spine_runtime import build_record, is_spine_event

if TYPE_CHECKING:
    from lca.contracts.event import EventPayload
    from lca_kernel.events.bus import EventRef

from pydantic import BaseModel

log = logging.getLogger(__name__)

_EXCEPTION_EP = "exception.caught"


class ExceptionIndexWriter:
    """Session observer: ``exception.caught`` → exceptions write-behind buffer."""

    def __init__(
        self,
        *,
        run_dir: Path | None = None,
        registry: RunWriteBehindRegistry | None = None,
    ) -> None:
        self._run_dir = run_dir
        self._registry = registry

    def _registry_or_default(self) -> RunWriteBehindRegistry:
        return self._registry if self._registry is not None else RunWriteBehindRegistry.default()

    def __call__(self, payload: EventPayload, ref: EventRef) -> None:
        if not is_spine_event(payload):
            return
        ep = getattr(payload, "execution_point", None)
        if ep != _EXCEPTION_EP:
            from lca_kernel.events.payloads_spine import category_to_spine_ep

            category = getattr(payload, "category", None)
            cat_value = getattr(category, "value", None) or str(category or "")
            if category_to_spine_ep(cat_value) != _EXCEPTION_EP:
                return
        try:
            record = build_record(payload, ref)
        except Exception:
            log.exception(
                "exception_index_writer: build_record failed event_id=%s",
                ref.event_id,
            )
            return
        if record.execution_point != _EXCEPTION_EP:
            return
        try:
            run_id_from_event_id(ref.event_id)
        except ValueError:
            log.warning(
                "exception_index_writer: skip without run context event_id=%s",
                ref.event_id,
            )
            return
        try:
            self._registry_or_default().enqueue_exception_line(
                ref.event_id,
                record.to_dict(),
                run_dir=self._run_dir,
            )
        except Exception:
            log.exception(
                "exception_index_writer: enqueue failed event_id=%s",
                ref.event_id,
            )


WRITER_PLUGIN_CLASS = ExceptionIndexWriter


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.subscriber.exception_index_writer",
    provides=["events.subscriber.exception_index"],
    requires=[],
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "ExceptionIndexWriter (ADR-0183): Session observer filtering "
        "exception.caught into per-run *.exceptions.jsonl via write-behind."
    ),
    test_suite="tests.plugins.events.subscribers.test_exception_index_writer",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.subscriber.consume",)),
        observability=EvidenceContract(descriptors=("events.exception_index.written",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(),
        state_mutation="forbidden",
    ),
    marker_class=WRITER_PLUGIN_CLASS,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    from lca.plugins.events._session_observe import register_as_session_observer

    writer = ExceptionIndexWriter()
    register_as_session_observer(WRITER_PLUGIN_CLASS, writer)
    ctx.provide("events.subscriber.exception_index", writer)


__all__ = ["WRITER_PLUGIN_CLASS", "ExceptionIndexWriter", "setup"]
