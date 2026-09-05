"""TokenUsageUnit —— token 计量投影（DSH token-meter 投影对位）。"""

from __future__ import annotations

from typing import Any

import structlog
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
from lca.plugins.session.token_meter.token_meter import (
    HeuristicTokenMeter,
    estimate_text_tokens,
)
from lca.plugins.session.runtime.messages import derive_event_message
from lca_kernel.events.fold import SURFACE_ASSISTANT_TYPE, SURFACE_TOOL_RESULT_TYPE, SURFACE_USER_TYPE
from lca_kernel.events.session import SessionEvent

_log = structlog.get_logger(__name__)

__all__ = ["Config", "TokenUsageUnit", "setup"]

_SURFACE_TYPES = frozenset({SURFACE_USER_TYPE, SURFACE_ASSISTANT_TYPE, SURFACE_TOOL_RESULT_TYPE})


class TokenUsageUnit:
    """增量 fold token 压力快照;``view`` 出口对齐 :class:`TokenMeterSnapshot` 字段。"""

    key: str = "token_usage"
    state_version: int = 1

    def init(self, header: Any) -> dict[str, Any]:
        del header
        return _empty_state()

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        next_state = dict(state)
        next_state["log_revision"] = event.seq + 1
        if event.type in _SURFACE_TYPES and event.surface_op is not None:
            msg = derive_event_message(event)
            if msg is not None:
                delta = estimate_text_tokens(_message_text(msg))
                next_state["surface_delta_tokens"] = state["surface_delta_tokens"] + delta
                next_state["surface_tokens"] = state["surface_tokens"] + delta
                nodes = list(state["nodes"])
                nodes.append({"seq": event.seq, "estimated_tokens": delta, "kind": "estimated"})
                next_state["nodes"] = nodes
        if event.type == "model.completed.v1":
            usage = event.data.get("usage")
            if isinstance(usage, dict):
                total = usage.get("total_tokens") or usage.get("total")
                if isinstance(total, int):
                    next_state["baseline"] = total
                    next_state["baseline_kind"] = "usage"
        next_state["total_tokens"] = next_state["baseline"] + next_state["surface_tokens"]
        return next_state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "log_revision": state["log_revision"],
            "baseline": state["baseline"],
            "surface_delta_tokens": state["surface_delta_tokens"],
            "total_tokens": state["total_tokens"],
            "surface_tokens": state["surface_tokens"],
            "nodes": tuple(state["nodes"]),
            "shadowed_token_count": state["shadowed_token_count"],
            "baseline_kind": state["baseline_kind"],
        }


def _empty_state() -> dict[str, Any]:
    return {
        "log_revision": 0,
        "baseline": 0,
        "surface_delta_tokens": 0,
        "total_tokens": 0,
        "surface_tokens": 0,
        "nodes": [],
        "shadowed_token_count": 0,
        "baseline_kind": "estimated",
    }


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return str(content)


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.plugins.session.token_usage",
    provides=["session.projection.token_usage", "session.token_meter"],
    requires=["session.projections"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "token_usage 投影单元 + HeuristicTokenMeter seam（DSH token-meter 对位）："
        "折 surface / model.completed 为 token 压力快照。"
    ),
    test_suite="tests/plugins/session/test_token_usage.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.projections",),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    unit = TokenUsageUnit()
    meter = HeuristicTokenMeter()
    ctx.provide("session.projection.token_usage", unit)
    ctx.provide("session.token_meter", meter)
    registry = ctx.soft_get("session.projections")
    if registry is None:
        _log.info("session.token_usage.no_registry", id="lca.plugins.session.token_usage")
        return
    registry.register(unit)
