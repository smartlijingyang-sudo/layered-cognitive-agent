"""CognitiveAgent — single agent runtime unit."""

from __future__ import annotations

import asyncio

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
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    adopt_run_scope,
)
from lca.contracts.models.team.partial_buffer import (
    begin_partial_buffer,
    drain_run_partial,
    reset_partial_buffer,
)
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols import AgentUnit, Runtime
from lca.contracts.protocols.capabilities import HasHooks
from lca.layer0_infra.observability import (
    ObservabilityHub,
    bind,
    objective_preview,
    record,
    run_scope,
    set_session,
)
from lca.layer0_infra.workspace import effective_agent_wall_clock, get_run_workspace

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
        scope, top_level = adopt_run_scope(role=role)
        if ctx and ctx.session_id:
            set_session(ctx.session_id)
        with bind(self._observability), run_scope(scope):
            partial_token = begin_partial_buffer()
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
                ctx = self._enrich_run_context(ctx)
                effective_wall = effective_agent_wall_clock(self.max_wall_clock_seconds)
                result = await self.runtime.run(
                    text,
                    ctx,
                    max_steps=self.max_steps,
                    max_wall_clock_seconds=effective_wall,
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
            except asyncio.CancelledError:
                # ADR-0049：deadline cancel 时收割 stream partial，不丢弃已生成正文
                finish_status = TaskStatus.CANCELED.value
                finish_output = drain_run_partial()
                finish_error = "canceled"
                raise
            except Exception as err:
                finish_status = TaskStatus.FAILED.value
                finish_output = drain_run_partial()
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
                reset_partial_buffer(partial_token)

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

    @staticmethod
    def _enrich_run_context(ctx: RunContext | None) -> RunContext | None:
        workspace = get_run_workspace()
        if workspace is None or workspace.deadline is None:
            return ctx
        if ctx is not None and ctx.deadline is not None:
            return ctx
        if ctx is None:
            return RunContext(deadline=workspace.deadline)
        return RunContext(
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
            from_role=ctx.from_role,
            context_refs=list(ctx.context_refs),
            deadline=workspace.deadline,
            team_awareness=ctx.team_awareness,
            extra=dict(ctx.extra),
        )

    def register_hook(self, hook_name: str, hook_fn: Hook) -> None:
        runtime = self.runtime
        if isinstance(runtime, HasHooks):
            runtime.hooks.register(hook_name, hook_fn)
