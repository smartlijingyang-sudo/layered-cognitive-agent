# COMPAT(owner: ADR-0194 P2-13, from: spine_reflector_body_llm plugin emit,
# to: lca.loop.llm_emit + lca.loop.tool_journal_commit,
# delete_when: rg "spine_reflector_body_llm" 生产引用归零(P2-16 bundle 已删),
# forbidden_new_usage: 新 emit 走 lca.loop.llm_emit / tool_journal_commit)
"""spine_reflector_body_llm COMPAT shim (ADR-0194 P2-13).

Body tool EPs → ``tool_journal_commit``; LLM EPs → ``llm_emit``.
Plugin marker retained for yaml auth / test catalog only.
"""

from __future__ import annotations

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
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.loop.llm_emit import (
    emit_llm_call_end,
    emit_llm_call_start,
    emit_llm_stream_stall,
    emit_llm_stream_token,
)
from lca.loop.spine_ep_emit import SpineEmitRef, receipt_or_none
from lca.loop.tool_journal_commit import (
    commit_body_sandbox_enter,
    commit_body_sandbox_exit,
    commit_body_tool_decision_end,
    commit_body_tool_decision_start,
    commit_body_tool_execute_end,
    commit_body_tool_execute_start,
    commit_body_tool_retry,
)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


class ReflectorClass:
    """Publisher marker for yaml auth matrix (legacy)."""


def _wrap(receipt: object | None) -> SpineEmitRef | None:
    from lca.contracts.protocols.loop.fact_gateway import AppendReceipt

    if isinstance(receipt, AppendReceipt):
        return receipt_or_none(receipt)
    return receipt  # type: ignore[return-value]


def emit_body_tool_execute_start(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int = 1,
) -> Any:
    return _wrap(
        commit_body_tool_execute_start(
            tool_name=tool_name,
            invocation_id=invocation_id,
            attempt=attempt,
        )
    )


def emit_body_tool_execute_end(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int = 1,
    outcome: str = "success",
    latency_ms: int | None = None,
) -> Any:
    return _wrap(
        commit_body_tool_execute_end(
            tool_name=tool_name,
            invocation_id=invocation_id,
            attempt=attempt,
            outcome=outcome,
            latency_ms=latency_ms,
        )
    )


def emit_body_tool_decision_start(*, tool_name: str, invocation_id: str) -> Any:
    return _wrap(
        commit_body_tool_decision_start(tool_name=tool_name, invocation_id=invocation_id)
    )


def emit_body_tool_decision_end(
    *,
    tool_name: str,
    invocation_id: str,
    outcome: str = "success",
) -> Any:
    return _wrap(
        commit_body_tool_decision_end(
            tool_name=tool_name,
            invocation_id=invocation_id,
            outcome=outcome,
        )
    )


def emit_body_tool_retry(
    *,
    tool_name: str,
    invocation_id: str,
    attempt: int,
    reason: str,
) -> Any:
    return _wrap(
        commit_body_tool_retry(
            tool_name=tool_name,
            invocation_id=invocation_id,
            attempt=attempt,
            reason=reason,
        )
    )


def emit_body_sandbox_enter(*, invocation_id: str, tool_name: str) -> Any:
    return _wrap(
        commit_body_sandbox_enter(invocation_id=invocation_id, tool_name=tool_name)
    )


def emit_body_sandbox_exit(
    *,
    invocation_id: str,
    tool_name: str,
    outcome: str = "success",
) -> Any:
    return _wrap(
        commit_body_sandbox_exit(
            invocation_id=invocation_id,
            tool_name=tool_name,
            outcome=outcome,
        )
    )


__all__ = [
    "ReflectorClass",
    "emit_body_sandbox_enter",
    "emit_body_sandbox_exit",
    "emit_body_tool_decision_end",
    "emit_body_tool_decision_start",
    "emit_body_tool_execute_end",
    "emit_body_tool_execute_start",
    "emit_body_tool_retry",
    "emit_llm_call_end",
    "emit_llm_call_start",
    "emit_llm_stream_stall",
    "emit_llm_stream_token",
    "setup",
]


@plugin(
    id="events.spine.reflector.body_llm",
    provides=["event.bus.reflector.body_llm"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="COMPAT: body/llm spine EPs migrated to lca.loop (ADR-0194 P2-13).",
    test_suite="tests/plugins/events/publishers/test_spine_reflector_body_llm.py",
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.body_llm.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.body.tool.execute.start",
            "spine.body.tool.execute.end",
            "spine.body.tool.retry",
            "spine.body.sandbox.enter",
            "spine.body.sandbox.exit",
            "spine.llm.call.start",
            "spine.llm.call.end",
            "spine.llm.stream.token",
            "spine.llm.stream.stall",
        ),
        state_mutation="forbidden",
    ),
    marker_class=ReflectorClass,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    del config
    ctx.provide("event.bus.reflector.body_llm", ReflectorClass)
