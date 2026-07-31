"""Uniform member call path for team process strategies."""

from __future__ import annotations

from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import AgentUnit, TeamContext
from lca.contracts.result import Result

_DEFAULT_TIMEOUT_S = 300.0


async def _call_local(member: AgentUnit, objective: str) -> Result:
    return await member.run(objective)


async def invoke_member(
    context: TeamContext,
    member: AgentUnit,
    objective: str,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Result:
    transport = context.transport
    if transport is not None:
        role = member.role_profile.role
        if role:
            task_id = await transport.send_task(role, objective, [])
            wait = getattr(transport, "wait_result", None)
            if wait is not None:
                observation = await wait(task_id, timeout_s)
            else:
                observation = await transport.receive_result(task_id)
            return Result.from_observation(observation, task_id)
    return await _call_local(member, objective)


async def invoke_members_sequential(
    context: TeamContext,
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
