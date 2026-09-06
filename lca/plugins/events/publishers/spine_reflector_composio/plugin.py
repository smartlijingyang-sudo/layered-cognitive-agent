"""spine_reflector_composio — durable spine for Composio connection + tool EPs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

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
from lca.contracts.observability.composio_ep_closure import COMPOSIO_EVENT_POINTS
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.domain_event_publish import publish_structural_event
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

_COMPOSIO_SPINE_CATEGORIES: tuple[str, ...] = tuple(
    _SPINE_EP_TO_CATEGORY[ep] for ep in COMPOSIO_EVENT_POINTS
)


class ReflectorClass:
    """Publisher marker for yaml auth matrix."""


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


def emit_composio_domain_event(
    *,
    execution_point: str,
    payload: Mapping[str, Any],
    channel: str = "fact",
) -> Any:
    """Publish one composio structural EP (Session spine when bound)."""
    return publish_structural_event(
        execution_point=execution_point,
        channel=channel,
        payload=dict(payload),
        producer=ReflectorClass,
    )


__all__ = [
    "ReflectorClass",
    "emit_composio_domain_event",
    "setup",
]


@plugin(
    id="events.spine.reflector.composio",
    provides=["event.bus.reflector.composio"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Composio integration publisher: Session spine for composio.* EPs.",
    test_suite="tests/plugins/events/publishers/test_spine_reflector_composio.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.composio.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=_COMPOSIO_SPINE_CATEGORIES,
        state_mutation="forbidden",
    ),
    marker_class=ReflectorClass,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    del config
    ctx.provide("event.bus.reflector.composio", ReflectorClass)
