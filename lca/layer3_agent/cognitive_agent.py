"""CognitiveAgent — single agent runtime unit."""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS
from lca.contracts.mechanisms import Hook
from lca.contracts.message import AgentMessage, agent_message_as_text, agent_message_text
from lca.contracts.protocols import AgentUnit, Observability, Runtime
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
    SpanName,
)
from lca.layer0_infra.observability import NullObservability, bind, get_span_context, span
from lca.layer0_infra.observability.plan_narrative import plan_steps_joined

_OBJECTIVE_PREVIEW_MAX = 240


def _task_as_text(task: str | AgentMessage) -> str:
    if isinstance(task, AgentMessage):
        return agent_message_as_text(task)
    return task


def _obs_from_runtime(runtime: Runtime) -> Observability:
    hooks = getattr(runtime, "hooks", None)
    obs = getattr(hooks, "observability", None)
    return obs if isinstance(obs, Observability) else NullObservability()


class CognitiveAgent(AgentUnit):
    """Runtime + RoleProfile as a schedulable unit with run / resume / cancel."""

    def __init__(
        self,
        runtime: Runtime,
        role_profile: RoleProfile,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
    ) -> None:
        self.runtime = runtime
        self.role_profile = role_profile
        self.max_steps = max_steps
        self.max_wall_clock_seconds = max_wall_clock_seconds

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result:
        text = _task_as_text(task)
        role = self.role_profile.role
        # Nested under Team: ambient parent exists → no second RUN_PLAN card.
        top_level = get_span_context().parent_span_id is None
        # Always bind at the agent edge (re-entrant if Team already bound).
        with (
            bind(_obs_from_runtime(self.runtime)),
            span(SpanName.RUN_AGENT, **{ATTR_AGENT_ROLE: role}) as handle,
        ):
            if top_level:
                with span(
                    SpanName.RUN_PLAN,
                    **{
                        ATTR_AGENT_ROLE: role,
                        ATTR_STRATEGY_KEY: "solo",
                        ATTR_OBJECTIVE_PREVIEW: text[:_OBJECTIVE_PREVIEW_MAX],
                        ATTR_PLAN_STEPS: plan_steps_joined("solo"),
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
