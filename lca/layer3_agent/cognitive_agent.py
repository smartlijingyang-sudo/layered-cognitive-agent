"""CognitiveAgent — single agent runtime unit."""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS
from lca.contracts.mechanisms import Hook
from lca.contracts.message import AgentMessage, agent_message_as_text, agent_message_text
from lca.contracts.protocols import AgentUnit, Runtime
from lca.contracts.protocols.capabilities import HasHooks
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile
from lca.contracts.run_context import RunContext
from lca.contracts.state import StateSnapshot
from lca.contracts.telemetry import (
    ATTR_AGENT_ROLE,
    ATTR_OBJECTIVE_PREVIEW,
    ATTR_PLAN_STEPS,
    ATTR_STATUS,
    ATTR_STRATEGY_KEY,
    EventName,
    SpanName,
)
from lca.layer0_infra.observability import (
    ObservabilityHub,
    bind,
    event,
    get_span_context,
    objective_preview,
    plan_steps_joined,
    set_session,
    span,
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
        # Nested under Team: ambient parent exists → no second RUN_PLAN card.
        top_level = get_span_context().parent_span_id is None
        if ctx and ctx.session_id:
            set_session(ctx.session_id)
        # Always bind at the agent edge (re-entrant if Team already bound).
        with (
            bind(self._observability),
            span(SpanName.RUN_AGENT, **{ATTR_AGENT_ROLE: role}) as handle,
        ):
            if top_level:
                with span(
                    SpanName.RUN_PLAN,
                    **{
                        ATTR_AGENT_ROLE: role,
                        ATTR_STRATEGY_KEY: _STRATEGY_KEY_SOLO,
                        ATTR_OBJECTIVE_PREVIEW: objective_preview(text),
                        ATTR_PLAN_STEPS: plan_steps_joined(_STRATEGY_KEY_SOLO),
                    },
                ):
                    pass
            result = await self.runtime.run(
                text,
                ctx,
                max_steps=self.max_steps,
                max_wall_clock_seconds=self.max_wall_clock_seconds,
                agent_role=role,
            )
            handle.attributes[ATTR_STATUS] = result.status
            if top_level:
                event(
                    EventName.RUN_COMPLETED,
                    **{ATTR_STATUS: result.status, "steps": result.total_steps},
                )
            return result

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
