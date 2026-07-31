"""Uniform member call path for team process strategies."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import cast

from lca.contracts.decision import ActResult
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import TeamContext
from lca.contracts.result import Result
from lca.contracts.state import Budget

_DEFAULT_TIMEOUT_S = 300.0


def observation_to_result(observation: ActResult, task_id: str) -> Result:
    """Convert ActResult from a channel path into Result."""
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


async def _call_local(member: object, objective: str) -> Result:
    """Prefer awaitable run/execute; skip non-awaitable mocks."""
    for name in ("run", "execute"):
        fn = getattr(member, name, None)
        if not callable(fn):
            continue
        out = fn(objective)
        if isinstance(out, Awaitable):
            return cast("Result", await out)
    return Result.failed("member has no run method")


async def invoke_member(
    context: TeamContext,
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


# Friendly alias
run_member = invoke_member
