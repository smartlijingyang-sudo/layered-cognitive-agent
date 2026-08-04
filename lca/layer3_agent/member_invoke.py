"""Uniform member call path for team process strategies."""

from __future__ import annotations

from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import AgentUnit, TeamContext
from lca.contracts.result import Result
from lca.contracts.telemetry import (
    ATTR_CALLEE_ROLE,
    ATTR_CALLER_ROLE,
    ATTR_OK,
    ATTR_STATUS,
    SpanName,
)
from lca.layer0_infra.observability import span
from lca.layer0_infra.transport.invocation import send_and_wait

_DEFAULT_TIMEOUT_S = 300.0


async def invoke_member(
    context: TeamContext,
    member: AgentUnit,
    objective: str,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    caller_role: str = "",
) -> Result:
    """Invoke one team member through the shared transport port."""
    transport = context.transport
    if transport is None:
        raise ValueError(
            "TeamContext.transport is required for member invocation; "
            "assemble teams via TeamComposer.compose_team / Team"
        )
    role = member.role_profile.role
    if not role:
        raise ValueError("member role_profile.role is required for transport invoke")

    with span(
        SpanName.TEAM_MEMBER_INVOKE,
        **{
            ATTR_CALLEE_ROLE: role,
            ATTR_CALLER_ROLE: caller_role or "strategy",
        },
    ) as handle:
        observation = await send_and_wait(transport, role, objective, timeout_s=timeout_s)
        result = Result.from_observation(observation, task_id=observation.extra.get("task_id", ""))
        handle.attributes[ATTR_STATUS] = result.status
        handle.attributes[ATTR_OK] = result.status == TaskStatus.COMPLETED
        return result


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
