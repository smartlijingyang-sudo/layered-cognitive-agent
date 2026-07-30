"""团队成员统一调用路径。

L3 层职责：
    提供 invoke_member 和 invoke_members_sequential 两个原子函数，
    屏蔽 Transport 远程调用与直接 execute 的差异。
    所有编排策略通过这两个函数调用成员，不直接依赖 BaseAgent 或 Transport。
"""

from __future__ import annotations

from typing import cast

from lca.contracts.decision import Observation
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import OrchestrationContext
from lca.contracts.result import Result
from lca.contracts.state import Budget

_DEFAULT_TIMEOUT_S = 300.0


def observation_to_result(observation: Observation, task_id: str) -> Result:
    """将 Observation 转换为 Result —— transport 路径的纯函数转换器。

    提取为独立函数以便单元测试覆盖状态映射边界条件。
    """
    status = TaskStatus.COMPLETED if observation.success else TaskStatus.FAILED
    output: str | None
    if isinstance(observation.payload, str):
        output = observation.payload
    elif observation.payload is not None:
        output = str(observation.payload)
    else:
        output = None
    return Result(
        trace_id=new_id("trace"),
        status=status,
        final_state_ref=f"transport://{task_id}",
        total_steps=1,
        budget_used=Budget(used_steps=1),
        output=output,
        error=observation.error,
    )


async def invoke_member(
    context: OrchestrationContext,
    member: object,
    objective: str,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Result:
    transport = context.transport
    role = getattr(getattr(member, "role_profile", None), "role", None)
    if transport is not None and role:
        task_id = await transport.send_task(role, objective, [])
        wait = getattr(transport, "wait_result", None)
        if wait is not None:
            observation = await wait(task_id, timeout_s)
        else:
            observation = await transport.receive_result(task_id)
        return observation_to_result(observation, task_id)
    execute = getattr(member, "execute", None)
    if execute is None:
        return Result.failed("member has no execute method")
    return cast("Result", await execute(objective))


async def invoke_members_sequential(
    context: OrchestrationContext,
    objective: str,
    *,
    pass_output_as_next_task: bool = True,
    stop_on_first_completed: bool = False,
) -> Result:
    if not context.members:
        return Result.failed("No members in team")
    current_task = objective
    last_result: Result | None = None
    total_steps = 0
    for member in context.members:
        last_result = await invoke_member(context, member, current_task)
        total_steps += last_result.total_steps
        if stop_on_first_completed and last_result.status == TaskStatus.COMPLETED:
            last_result.total_steps = total_steps
            return last_result
        if pass_output_as_next_task and last_result.output:
            current_task = last_result.output
    if last_result is None:
        return Result.failed("No members in team")
    last_result.total_steps = total_steps
    return last_result
