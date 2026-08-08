"""CognitiveAgent — single agent runtime unit."""

from __future__ import annotations

from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms import Hook
from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.message import (
    AgentMessage,
    agent_message_as_text,
    agent_message_text,
)
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import StateSnapshot
from lca.contracts.models.observability.journal import AgentRunFinished, AgentRunStarted, RunScope
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols import AgentUnit, Runtime
from lca.contracts.protocols.capabilities import HasHooks
from lca.layer0_infra.observability import (
    ObservabilityHub,
    bind,
    get_current_run_scope,
    objective_preview,
    record,
    run_scope,
    set_session,
)

_STRATEGY_KEY_SOLO = "solo"


def _task_as_text(task: str | AgentMessage) -> str:
    if isinstance(task, AgentMessage):
        return agent_message_as_text(task)
    return task


class CognitiveAgent(AgentUnit):
    """Runtime + RoleProfile as a schedulable unit with run / resume / cancel."""

    def __init__(
        self,
        runtime: Runtime,
        role_profile: RoleProfile,
        observability: ObservabilityHub,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
    ) -> None:
        self.runtime = runtime
        self.role_profile = role_profile
        self._observability = observability
        self.max_steps = max_steps
        self.max_wall_clock_seconds = max_wall_clock_seconds

    @property
    def observability(self) -> ObservabilityHub:
        """组合注入的观测 hub（只读暴露，供组合根提升/复用）。"""
        return self._observability

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result:
        text = _task_as_text(task)
        role = self.role_profile.role
        # 关联骨架：继承委派方 scope（成员），无则为 solo 根 run。
        inherited = get_current_run_scope()
        top_level = inherited is None
        scope = RunScope(
            trace_id=inherited.trace_id if inherited else new_id("trace"),
            run_id=new_id("run"),
            parent_run_id=inherited.run_id if inherited else None,
            delegation_id=inherited.delegation_id if inherited else None,
            agent_role=role,
        )
        if ctx and ctx.session_id:
            set_session(ctx.session_id)
        with bind(self._observability), run_scope(scope):
            record(
                AgentRunStarted(
                    agent_role=role,
                    strategy_key=_STRATEGY_KEY_SOLO if top_level else "",
                    objective=text,
                    objective_preview=objective_preview(text),
                    from_role=ctx.from_role if ctx else "",
                )
            )
            # 默认 CANCELED：CancelledError 是 BaseException，不会进 except Exception。
            # finally 保证任何退出路径都发射 Finished，OTel attach 在同 task 配对 detach。
            finish_status = TaskStatus.CANCELED.value
            finish_output = ""
            finish_steps = 0
            finish_error = ""
            try:
                result = await self.runtime.run(
                    text,
                    ctx,
                    max_steps=self.max_steps,
                    max_wall_clock_seconds=self.max_wall_clock_seconds,
                    agent_role=role,
                )
                finish_status = (
                    result.status.value
                    if isinstance(result.status, TaskStatus)
                    else str(result.status)
                )
                finish_output = result.output or ""
                finish_steps = result.total_steps
                finish_error = result.error or ""
                return result
            except Exception as err:
                finish_status = TaskStatus.FAILED.value
                finish_error = f"{type(err).__name__}: {err}"
                raise
            finally:
                record(
                    AgentRunFinished(
                        status=finish_status,
                        output_text=finish_output,
                        steps=finish_steps,
                        error=finish_error,
                    )
                )

    async def resume(
        self,
        snapshot: StateSnapshot,
        input: str | AgentMessage | None = None,
    ) -> Result:
        msg = None
        if isinstance(input, AgentMessage):
            msg = input
        elif isinstance(input, str):
            msg = agent_message_text(input)
        return await self.runtime.resume(snapshot, input=msg, max_steps=self.max_steps)

    async def cancel(self) -> None:
        return None

    def register_hook(self, hook_name: str, hook_fn: Hook) -> None:
        runtime = self.runtime
        if isinstance(runtime, HasHooks):
            runtime.hooks.register(hook_name, hook_fn)
