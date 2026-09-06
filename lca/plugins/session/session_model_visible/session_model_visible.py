"""ModelVisibleUnit — incremental surface → messages projection (ADR-0193)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.session.runtime.messages import derive_event_message
from lca_kernel.events.fold import SurfaceReplaceOp, isSurfaceEvent
from lca_kernel.events.session import SessionEvent

__all__ = ["Config", "ModelVisibleUnit", "setup"]

_PROJECTION_KEY = "model_visible"


def _empty_state() -> dict[str, Any]:
    return {"nodes": [], "messages": []}


def _surface_op(event: SessionEvent) -> str | SurfaceReplaceOp | None:
    op = event.surface_op
    if op is None:
        return None
    if op == "append":
        return "append"
    if isinstance(op, dict) and op.get("op") == "replace":
        start = op.get("start")
        end = op.get("end")
        if isinstance(start, int) and isinstance(end, int):
            return SurfaceReplaceOp(op="replace", start=start, end=end)
    if hasattr(op, "op") and getattr(op, "op", None) == "replace":
        return op  # type: ignore[return-value]
    return None


def _apply_surface(state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
    if not isSurfaceEvent(event):
        return state
    surface_op = _surface_op(event)
    if surface_op is None:
        return state
    nodes = list(state["nodes"])
    messages = list(state["messages"])
    if surface_op == "append":
        msg = derive_event_message(event)
        if msg is None:
            return state
        nodes.append(event.seq)
        messages.append(msg)
        return {"nodes": nodes, "messages": messages}
    if isinstance(surface_op, SurfaceReplaceOp):
        try:
            start_idx = nodes.index(surface_op.start)
            end_idx = nodes.index(surface_op.end)
        except ValueError:
            return state
        if start_idx > end_idx:
            return state
        msg = derive_event_message(event)
        if msg is None:
            return state
        nodes[start_idx : end_idx + 1] = [event.seq]
        messages[start_idx : end_idx + 1] = [msg]
        return {"nodes": nodes, "messages": messages}
    return state


class ModelVisibleUnit:
    """Incremental fold of model-visible surface nodes → provider messages."""

    key: str = _PROJECTION_KEY
    state_version: int = 1

    def init(self, header: Any) -> dict[str, Any]:
        del header
        return _empty_state()

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        next_state = _apply_surface(state, event)
        if next_state is state:
            return state
        return next_state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"messages": list(state["messages"])}


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.plugins.session.model_visible",
    Config=Config,
    provides=("session.projection.model_visible",),
    requires=("session.projections",),
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    test_suite="tests/plugins/session/test_model_visible_projection.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G3_FACTS,
            control_slots=(),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.projections",),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    unit = ModelVisibleUnit()
    ctx.provide("session.projection.model_visible", unit)
    registry = ctx.soft_get("session.projections")
    if registry is None:
        return
    registry.register(unit)
