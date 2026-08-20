"""Loop-provider routing for the legacy ``/runs`` compatibility carrier.

The carrier selects a registered provider; it does not know about DSH or an
LCA cognitive loop.  Production composition owns the default registrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from gateway.assemble import build_runnable_team, build_solo_agent
from gateway.modes import SOLO_MODE_KEY
from gateway.runs.dsh_execute import execute_dsh_session
from gateway.runs.session import RunSession
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.team.run_context import RunContext
from lca.layer0_infra.observability import ObservabilityHub
from lca.layer4_app.api import Agent, ensure_default_ctx


@dataclass(frozen=True)
class DriverOutcome:
    success: bool
    result: Any | None = None
    waiting_input: bool = False
    snapshot: Any = None
    approval_request: dict[str, Any] | None = None
    resumable: Any | None = None
    error: str = ""


class RunLoopDriver(Protocol):
    """A loop provider available to the legacy HTTP carrier."""

    uses_sandbox: bool
    plane_target: str | None

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: ObservabilityHub,
        bindings: Any,
        run_context: RunContext,
        llm_resolver: Any,
    ) -> DriverOutcome: ...


def _record_inbox_followup(
    *,
    session: RunSession,
    question: str,
    mode: str,
    run_context: RunContext,
) -> None:
    """Emit ``InboxFollowupCreated`` on the ambient RunStore (PR8.E.1 / D24).

    ``InboxFactsSensor`` reads these events to feed user messages into
    the next Perceive step.  No more bare ``run(question)`` — every
    user input enters via the Inbox followup.  The question text lives
    on the event's ``step`` metadata via RunScope; for simplicity we
    truncate to 200 chars and store on the agent session.
    """
    try:
        from lca.contracts.models.observability.journal import InboxFollowupCreated
        from lca.layer0_infra.observability import record

        priority = "task" if mode == "solo" else "background"
        target = "next_turn"
        record(
            InboxFollowupCreated(
                inbox_id=f"inbox-{session.run_id}-{_COUNTER.next()}",
                actor="user",
                target=target,
                priority=priority,
                step=0,
                payload_preview=question[:200] if isinstance(question, str) else "",
            )
        )
        # Also stash the question on the session so downstream readers
        # can pull it back without parsing the journal payload.
        if isinstance(question, str) and question:
            session.user_text = question[:200]
    except Exception:  # noqa: BLE001
        # Best-effort: if hub not bound (e.g. dry scripts), skip.
        pass


class _Counter:
    """Monotonic inbox-id counter for followup events."""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n


_COUNTER = _Counter()


class CognitiveRunDriver:
    uses_sandbox = True
    plane_target: str | None = None

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: ObservabilityHub,
        bindings: Any,
        run_context: RunContext,
        llm_resolver: Any,
    ) -> DriverOutcome:
        # PR8.E.1 / D24: every user input enters the loop via Inbox followup
        # (v3 §10.1).  Record ``InboxFollowupCreated`` so ``InboxFactsSensor``
        # can fold it into the next Perceive (no more bare ``run(question````).
        _record_inbox_followup(
            session=session,
            question=question,
            mode=mode,
            run_context=run_context,
        )
        llm = llm_resolver.resolve(mode=mode)
        scope = await ensure_default_ctx()
        if mode == SOLO_MODE_KEY:
            runnable = build_solo_agent(
                llm,
                observability=hub,
                role=session.agent.name,
                bindings=bindings,
                scope=scope,
            )
        else:
            runnable = await build_runnable_team(
                question,
                llm,
                observability=hub,
                trace_id=session.trace_id,
                run_id=session.run_id,
                bindings=bindings,
                plugin_ctx=scope,
            )
        result = (
            await runnable.run(question, run_context)
            if isinstance(runnable, Agent)
            else await runnable.run(question)
        )
        if result.status == TaskStatus.INPUT_REQUIRED:
            return DriverOutcome(
                success=False,
                result=result,
                waiting_input=True,
                snapshot=result.extra.get("state_snapshot"),
                approval_request=result.extra.get("approval_request"),
                resumable=runnable,
            )
        return DriverOutcome(
            success=result.status == TaskStatus.COMPLETED,
            result=result,
            error=result.error or "",
        )


class DshRunDriver:
    uses_sandbox = False
    plane_target = "device"

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: ObservabilityHub,
        bindings: Any,
        run_context: RunContext,
        llm_resolver: Any,
    ) -> DriverOutcome:
        del question, mode, hub, bindings, run_context, llm_resolver
        await execute_dsh_session(session)
        return DriverOutcome(success=not session.error, error=session.error)


class RunLoopDriverRegistry:
    """Target-to-provider registry; plugins can replace either provider."""

    def __init__(self, fallback: RunLoopDriver) -> None:
        self._fallback = fallback
        self._drivers: dict[str, RunLoopDriver] = {}

    def register(self, target: str, driver: RunLoopDriver) -> None:
        self._drivers[target.strip().lower()] = driver

    def resolve(self, target: str) -> RunLoopDriver:
        return self._drivers.get(target.strip().lower(), self._fallback)


DEFAULT_RUN_DRIVERS = RunLoopDriverRegistry(CognitiveRunDriver())
DEFAULT_RUN_DRIVERS.register("dsh", DshRunDriver())
