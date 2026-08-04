"""成员调用通道 —— TransportMemberInvoker 与接力式共享逻辑（ADR-0034）。

策略经组合期注入的 invoker 调用成员：策略侧不认 transport，角色合法性
由组合期 fail-fast 保证，运行期零防御性校验。
"""

from __future__ import annotations

from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import AgentUnit, MemberInvoker, TeamStage
from lca.contracts.protocols.infra import AgentTransport
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


class TransportMemberInvoker(MemberInvoker):
    """组合期绑定的成员调用通道：成员角色 → transport ``send_and_wait``。"""

    def __init__(self, transport: AgentTransport, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self._transport = transport
        self._timeout_s = timeout_s

    async def invoke(self, member: AgentUnit, task: str, *, caller_role: str = "") -> Result:
        """通过共享 transport 端口调用一个成员。"""
        role = member.role_profile.role
        with span(
            SpanName.TEAM_MEMBER_INVOKE,
            **{
                ATTR_CALLEE_ROLE: role,
                ATTR_CALLER_ROLE: caller_role or "strategy",
            },
        ) as handle:
            observation = await send_and_wait(
                self._transport, role, task, timeout_s=self._timeout_s
            )
            result = Result.from_observation(
                observation, task_id=observation.extra.get("task_id", "")
            )
            handle.attributes[ATTR_STATUS] = result.status
            handle.attributes[ATTR_OK] = result.status == TaskStatus.COMPLETED
            return result


async def invoke_members_sequential(
    stage: TeamStage,
    objective: str,
    *,
    pass_output_as_next_task: bool = True,
    stop_on_first_completed: bool = False,
) -> Result:
    """接力式编排共享逻辑（Pipeline 链式输出 / PeerRelay 首个完成即赢）。"""
    members = stage.members
    if not members:
        return Result.failed("No members in team")
    current_task = objective
    last_result: Result | None = None
    total_steps = 0
    for member in members:
        last_result = await stage.invoker.invoke(member, current_task)
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
