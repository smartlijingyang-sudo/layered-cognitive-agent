"""Session Service Definition plugin — Tier-1.

Migrated from lca/plugins/session_service/__init__.py. The full SessionService
implementation (with agent_service merge) lives in Task 2.4.5 follow-up work.

For now, this provides a minimal SessionService that records events.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.session_events import SessionEventType
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class SessionService:
    """Session store + surface projection (model-visible ⟺ logged)."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    async def record(
        self, event_type: SessionEventType, session_id: str, **payload: object
    ) -> None:
        self._events.append({"type": event_type.value, "session_id": session_id, **payload})


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-session-service",
    provides=["session_service"],
    layer="L0",
    effects="none",
    description="Minimal SessionService — full implementation deferred.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-session-service.checked', 'lca-session-service.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.provide("session_service", SessionService())
