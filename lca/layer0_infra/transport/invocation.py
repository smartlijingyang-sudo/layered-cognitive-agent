"""成员调用的唯一 transport 通道（阻塞 send_and_wait + 非阻塞 handoff）。

ADR-0037：**委派叙事在此单点发射**——阻塞路径 record DelegationIssued /
DelegationCompleted（一等公民事件，OtelProjector 投影为包住成员全程的
delegation span），非阻塞路径 record DelegationIssued(handoff) 事件。
关联骨架（caller run_id + delegation_id）经 ``delegation_scope`` 穿透
asyncio.create_task 边界，成员 run 由此派生 parent_run_id / delegation_id。
``transport.request/response`` 仍是机制平面 span（verbose 档调试细节）。
"""

from __future__ import annotations

from lca.contracts.decision import Observation
from lca.contracts.delegation_context import (
    delegation_scope,
    get_delegator_context,
    in_member_invoke,
)
from lca.contracts.ids import new_id
from lca.contracts.journal import (
    DelegationCompleted,
    DelegationIssued,
    DelegationMechanism,
    RunScope,
    get_current_run_scope,
    run_scope,
)
from lca.contracts.lifecycle import AgentCard, TaskStatus
from lca.contracts.protocols import AgentTransport
from lca.contracts.semantic_keys import OBS_TASK_ID
from lca.contracts.telemetry import ATTR_CALLEE_ROLE, ATTR_OK, ATTR_PROTOCOL, SpanName
from lca.layer0_infra.observability import record, span

_DEFAULT_TIMEOUT_S = 300.0


def _describe_target(agent_card: AgentCard | str) -> str:
    return (
        agent_card if isinstance(agent_card, str) else getattr(agent_card, "role", str(agent_card))
    )


def _caller_role() -> str:
    """委派发起者角色：当前 run 的角色（lead）→ 退回上层委派者。"""
    scope = get_current_run_scope()
    if scope is not None and scope.agent_role:
        return scope.agent_role
    return get_delegator_context().role


def _current_run_id() -> str:
    scope = get_current_run_scope()
    return scope.run_id if scope is not None else ""


def _mechanism() -> DelegationMechanism:
    return DelegationMechanism.MEMBER_INVOKE if in_member_invoke() else DelegationMechanism.DELEGATE


def _payload_preview(payload: object) -> str:
    if payload is None:
        return ""
    return payload if isinstance(payload, str) else str(payload)


async def send_task_traced(
    transport: AgentTransport,
    agent_card: AgentCard | str,
    subtask: str,
    context_refs: list[str],
) -> str:
    """发送子任务（机制平面 transport.request span 的唯一发射点）。"""
    callee = _describe_target(agent_card)
    protocol = getattr(transport, "protocol_name", "unknown")
    with span(
        SpanName.TRANSPORT_REQUEST,
        **{ATTR_CALLEE_ROLE: callee, ATTR_PROTOCOL: protocol},
    ) as handle:
        task_id = await transport.send_task(agent_card, subtask, context_refs)
        handle.attributes[ATTR_OK] = True
    return task_id


async def send_and_wait(
    transport: AgentTransport,
    agent_card: AgentCard | str,
    subtask: str,
    context_refs: list[str] | None = None,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Observation:
    """Send a subtask via *transport* and wait for the Observation result.

    委派叙事一等公民：Issued（开）→ 传输往返 → Completed（闭），
    delegation_id 穿透到成员任务（成员 run 的关联骨架由此派生）。
    """
    refs = list(context_refs or [])
    callee = _describe_target(agent_card)
    protocol = getattr(transport, "protocol_name", "unknown")

    delegation_id = new_id("dlg")
    caller_scope = get_current_run_scope()
    record(
        DelegationIssued(
            delegation_id=delegation_id,
            caller_role=_caller_role(),
            callee_role=callee,
            subtask_preview=subtask,
            mechanism=_mechanism(),
        )
    )
    # 成员 scope：parent_run_id=发起方 run_id，delegation_id=本次委派。
    # create_task 拷贝 contextvars，成员任务由此继承关联骨架；
    # 等待阶段恢复发起方自己的 scope（成员 scope 只在调度瞬间生效）。
    member_scope = RunScope(
        trace_id=caller_scope.trace_id if caller_scope else "",
        run_id="",
        parent_run_id=caller_scope.run_id if caller_scope else None,
        delegation_id=delegation_id,
        agent_role=callee,
    )
    with delegation_scope(_caller_role(), _current_run_id(), delegation_id):
        with run_scope(member_scope):
            task_id = await send_task_traced(transport, agent_card, subtask, refs)

        with span(
            SpanName.TRANSPORT_RESPONSE,
            **{ATTR_CALLEE_ROLE: callee, ATTR_PROTOCOL: protocol, "task_id": task_id},
        ) as handle:
            wait = getattr(transport, "wait_result", None)
            if wait is not None and timeout_s > 0:
                waited = await wait(task_id, timeout_s)
                if not isinstance(waited, Observation):
                    raise TypeError(
                        f"wait_result must return Observation, got {type(waited).__name__}"
                    )
                observation = waited
            elif timeout_s <= 0:
                observation = Observation(
                    observation_id=f"obs_{task_id}",
                    success=False,
                    payload=None,
                    error=f"delegate 超时(deadline 已过期): task_id={task_id}",
                )
            else:
                observation = await transport.receive_result(task_id)
            handle.attributes[ATTR_OK] = observation.success
    record(
        DelegationCompleted(
            delegation_id=delegation_id,
            ok=observation.success,
            status=(TaskStatus.COMPLETED.value if observation.success else TaskStatus.FAILED.value),
            output_preview=_payload_preview(observation.payload),
            task_id=task_id,
        )
    )
    extra = dict(observation.extra or {})
    extra[OBS_TASK_ID] = task_id
    observation.extra = extra
    return observation


async def handoff_task_traced(
    transport: AgentTransport,
    agent_card: AgentCard | str,
    subtask: str,
    context_refs: list[str],
) -> str:
    """非阻塞控制权移交：record DelegationIssued(handoff)，发完即返回。"""
    callee = _describe_target(agent_card)
    delegation_id = new_id("dlg")
    record(
        DelegationIssued(
            delegation_id=delegation_id,
            caller_role=_caller_role(),
            callee_role=callee,
            subtask_preview=subtask,
            mechanism=DelegationMechanism.HANDOFF,
        )
    )
    with delegation_scope(_caller_role(), _current_run_id(), delegation_id):
        return await send_task_traced(transport, agent_card, subtask, context_refs)
