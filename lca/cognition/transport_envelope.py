"""A2A transport 的 CommandEnvelope 网关。"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.observability.plan_ref import get_current_plan_ref
from lca.contracts.protocols.command_envelope import CapabilityGrant, CommandEnvelope, mint_envelope
from lca.infrastructure.transport.invocation import handoff_task_traced, send_and_wait


def mint_transport_envelope(
    *,
    operation: str,
    decision_ref: str,
    protocol: str,
    target: str,
) -> CommandEnvelope:
    """为 transport effect 创建不可变封套。

    RuntimeKernel owns the compiled act.* controls.  This transport helper must
    not mint synthetic allow facts before that control boundary has executed.
    """
    plan_ref = get_current_plan_ref() or "legacy-transport"
    return mint_envelope(
        plan_ref=plan_ref,
        scope_ref="turn",
        decision={"decision_id": decision_ref},
        provider=f"transport:{protocol}",
        grant=CapabilityGrant(capability="transport", scope="turn", effect_class="transport"),
        idempotency_key=f"{operation}:{decision_ref}:{target}",
        policy_verdict_refs=(),
        metadata={
            "operation": operation,
            "protocol": protocol,
            "target": target,
            "plan_ref_source": "compiled" if plan_ref != "legacy-transport" else "compatibility",
        },
    )


async def delegate_via_envelope(
    transport: Any,
    agent_card: Any,
    subtask: str,
    context_refs: list[str],
    *,
    timeout_s: float,
    decision_ref: str,
    protocol: str,
) -> tuple[Any, CommandEnvelope]:
    """封套化地执行阻塞委派，并返回结果与封套证据。"""
    envelope = mint_transport_envelope(
        operation="delegate",
        decision_ref=decision_ref,
        protocol=protocol,
        target=str(agent_card),
    )
    result = await send_and_wait(transport, agent_card, subtask, context_refs, timeout_s=timeout_s)
    return result, envelope


async def handoff_via_envelope(
    transport: Any,
    agent_card: Any,
    subtask: str,
    context_refs: list[str],
    *,
    decision_ref: str,
    protocol: str,
) -> tuple[str, CommandEnvelope]:
    """封套化地执行非阻塞移交，并返回任务标识与封套证据。"""
    envelope = mint_transport_envelope(
        operation="handoff",
        decision_ref=decision_ref,
        protocol=protocol,
        target=str(agent_card),
    )
    task_id = await handoff_task_traced(transport, agent_card, subtask, context_refs)
    return task_id, envelope


__all__ = ["delegate_via_envelope", "handoff_via_envelope", "mint_transport_envelope"]
