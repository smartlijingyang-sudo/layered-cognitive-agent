"""TeamHandle —— 封闭团队的运行句柄：策略即行为，句柄只是叙事边缘（ADR-0037）。

团队的一切编排决策在组合期已闭合进 ``TeamStrategy``；句柄运行期不编排，
只做三件事：bind 观测 hub → record 团队 run 容器（场景卡随事件投影）→
委派策略。span 拓扑由 OtelProjector 从 journal 生成，句柄不接触 span。
成员与 lead 以只读属性暴露，供组合无损性内省。
"""

from __future__ import annotations

import contextlib

from lca.agent.run_envelope import (
    EnvelopeSpec,
    RunEventSessionBinder,
    TranslatedOutcome,
    run_envelope,
)
from lca.contracts.models.core.conversation.message import AgentMessage, agent_message_as_text
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.observability.journal.journal import (
    RunScope,
    TeamRunFinished,
    TeamRunStarted,
)
from lca.contracts.protocols import AgentUnit, TeamStrategy, TeamUnit
from lca.infrastructure.observability import (
    TEAM_CONTAINER_ROLE,
    BoundObservability,
    TeamTraceProfile,
    adopt_run_scope,
    bind_backends,
    objective_preview,
    plan_steps_joined,
    record,
    run_scope,
    set_session,
)


def _team_translate_success(result: Result) -> TranslatedOutcome:
    """Team flavor of execute() success: finish facts mirror the Result.

    Note: unlike the agent flavor, finish_error is NOT taken from
    result.error (pre-convergence behavior preserved byte-identically).
    """
    return TranslatedOutcome(
        status=result.status.value if isinstance(result.status, TaskStatus) else str(result.status),
        output=result.output or "",
        steps=result.total_steps,
        error="",
        outcome="success",
        disposition="return",
        result=result,
    )


def _team_translate_cancelled() -> TranslatedOutcome:
    """Team flavor of CancelledError.

    The team has no CancelledError branch: CancelledError is BaseException and
    skips except Exception, so the finally records the CANCELED defaults with
    outcome "success". Preserved byte-identically (odd but current).
    """
    return TranslatedOutcome(
        status=TaskStatus.CANCELED.value,
        output="",
        steps=0,
        error="",
        outcome="success",
        disposition="raise",
    )


def _team_translate_loop_obligation(err: BaseException) -> TranslatedOutcome:
    """Team flavor of non-convergence.

    The team has no loop-obligation branch: such an error falls into
    except Exception. Kept identical to _team_translate_error.
    """
    return _team_translate_error(err)


def _team_translate_error(err: Exception) -> TranslatedOutcome:
    """Team flavor of unexpected error: fail-loud."""
    return TranslatedOutcome(
        status=TaskStatus.FAILED.value,
        output="",
        steps=0,
        error=f"{type(err).__name__}: {err}",
        outcome="failure",
        disposition="raise",
    )


class TeamHandle(TeamUnit):
    """Holds a closed TeamStrategy + trace profile. Zero mutation on agents."""

    def __init__(
        self,
        strategy: TeamStrategy,
        profile: TeamTraceProfile,
        observability: BoundObservability,
        members: tuple[AgentUnit, ...],
        lead: AgentUnit | None = None,
        event_session_binder: RunEventSessionBinder | None = None,
    ) -> None:
        self._strategy = strategy
        self._profile = profile
        self._observability = observability
        self.members = members
        self.lead = lead
        self._event_session_binder = event_session_binder

    async def run(self, objective: str | AgentMessage) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        set_session(self._profile.team_id)
        scope, _ = adopt_run_scope(role=TEAM_CONTAINER_ROLE)
        # PR-3.1: spine envelope for the agent_loop.iteration execution
        # point on the team entry. The team is a closed strategy; one
        # ``TeamHandle.run`` is one iteration (the cognitive loop sits
        # inside each member agent).
        iteration_trace_id = scope.trace_id
        iteration_role = f"team:{self._profile.team_id}"

        binder = self._event_session_binder
        bound_cm = (
            binder.bound(scope.run_id)
            if binder is not None
            else contextlib.nullcontext()
        )

        with bound_cm:
            return await self._run_body(
                text,
                scope,
                iteration_trace_id,
                iteration_role,
            )

    async def _run_body(
        self,
        text: str,
        scope: RunScope,
        iteration_trace_id: str,
        iteration_role: str,
    ) -> Result:
        """Run one team iteration inside the shared envelope (RA-082).

        The team only supplies its Started/Finished factories and outcome
        translations; the try/except/finally cascade lives in
        lca.agent.run_envelope.run_envelope (shared with CognitiveAgent).
        """
        from lca.infrastructure.session.bindings import active_publish_session

        def emit_started() -> None:
            # 热路径 cheap 检查(todo-38,2026-10-05 裁决):event_session_binder
            # 缺席时无 Session,跳过,不抛 RuntimeError。
            if active_publish_session() is not None:
                record(
                    TeamRunStarted(
                        team_id=self._profile.team_id,
                        strategy_key=self._profile.strategy_key,
                        mandate=self._profile.mandate or "",
                        lead_role=self._profile.lead_role,
                        members=self._profile.member_roles,
                        objective=text,
                        objective_preview=objective_preview(text),
                        plan_steps=plan_steps_joined(
                            self._profile.strategy_key, self._profile.mandate
                        ),
                    )
                )

        def emit_finished(status: str, output: str, steps: int, error: str) -> None:
            # 热路径 cheap 检查(todo-38,2026-10-05 裁决):ContextVar 按上下文隔离,每次现查。
            if active_publish_session() is not None:
                record(
                    TeamRunFinished(
                        status=status,
                        output_text=output,
                        steps=steps,
                        error=error,
                    )
                )

        spec = EnvelopeSpec(
            iteration_kind="fresh",
            trace_id=iteration_trace_id,
            role=iteration_role,
            begin_section=lambda: None,
            emit_started=emit_started,
            emit_resumed=lambda: None,
            translate_success=_team_translate_success,
            translate_cancelled=_team_translate_cancelled,
            translate_loop_obligation=_team_translate_loop_obligation,
            translate_error=_team_translate_error,
            emit_finished=emit_finished,
            end_section=lambda _token: None,
        )

        async def execute() -> Result:
            return await self._strategy.run(text)

        with bind_backends(self._observability), run_scope(scope):
            return await run_envelope(spec=spec, execute=execute)
