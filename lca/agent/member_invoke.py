"""成员调用通道 —— TransportMemberInvoker 与接力式共享逻辑（ADR-0034/0037）。

策略经组合期注入的 invoker 调用成员：策略侧不认 transport，角色合法性
由组合期 fail-fast 保证，运行期零防御性校验。委派叙事（DelegationIssued/
Completed）由 transport 唯一通道发射，本模块只标记 member_invoke 机制。
"""

from __future__ import annotations

from lca.contracts.models.core.budget import DEFAULT_DELEGATION_TIMEOUT_S
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.team.delegation_context import member_invoke_scope
from lca.contracts.protocols import AgentUnit, MemberInvoker, TeamStage
from lca.contracts.protocols.runtime.infra import AgentTransport
from lca.infrastructure.transport.invocation import send_and_wait


def _workspace_handoff_prefix() -> str:
    from lca.infrastructure.workspace import get_run_workspace

    workspace = get_run_workspace()
    if workspace is None:
        return ""
    return workspace.artifacts.handoff_block()


class TransportMemberInvoker(MemberInvoker):
    """组合期绑定的成员调用通道：成员角色 → transport ``send_and_wait``。"""

    def __init__(
        self, transport: AgentTransport, timeout_s: float = DEFAULT_DELEGATION_TIMEOUT_S
    ) -> None:
        self._transport = transport
        self._timeout_s = timeout_s

    async def invoke(self, member: AgentUnit, task: str, *, caller_role: str = "") -> Result:
        """通过共享 transport 端口调用一个成员。"""
        del caller_role  # 调用者身份由 journal 关联骨架承载（scope.agent_role）
        role = member.role_profile.role
        with member_invoke_scope():
            observation = await send_and_wait(
                self._transport, role, task, timeout_s=self._timeout_s
            )
        return Result.from_observation(observation, task_id=observation.extra.get("task_id", ""))


async def invoke_members_sequential(
    stage: TeamStage,
    objective: str,
    *,
    pass_output_as_next_task: bool = True,
    stop_on_first_completed: bool = False,
) -> Result:
    """接力式编排共享逻辑（Pipeline 链式输出 / PeerRelay 首个完成即赢）。

    错误隔离：单成员失败时停止链式传递，返回已有最佳结果。
    """
    members = stage.members
    if not members:
        return Result.failed("No members in team")
    current_task = objective
    last_result: Result | None = None
    total_steps = 0
    handoff = _workspace_handoff_prefix()
    if handoff:
        current_task = f"{current_task}\n\n{handoff}"
    for member in members:
        try:
            last_result = await stage.invoker.invoke(member, current_task)
        except Exception as exc:
            # 成员调用异常：停止链式传递，返回已有最佳结果
            if last_result is not None:
                last_result.total_steps = total_steps
                return last_result
            return Result.failed(f"member {member.role_profile.role} failed: {exc}")
        total_steps += last_result.total_steps
        if stop_on_first_completed and last_result.status == TaskStatus.COMPLETED:
            last_result.total_steps = total_steps
            return last_result
        if pass_output_as_next_task and last_result.output:
            current_task = last_result.output
            handoff = _workspace_handoff_prefix()
            if handoff:
                current_task = f"{current_task}\n\n{handoff}"
    if last_result is None:
        return Result.failed("No members in team")
    last_result.total_steps = total_steps
    return last_result
