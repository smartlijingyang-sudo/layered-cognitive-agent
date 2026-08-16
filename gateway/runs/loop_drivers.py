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
from lca.layer4_app.api import Agent


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
        llm = llm_resolver.resolve(mode=mode)
        if mode == SOLO_MODE_KEY:
            runnable = build_solo_agent(
                llm,
                observability=hub,
                role=session.agent.name,
                bindings=bindings,
            )
        else:
            runnable = await build_runnable_team(
                question,
                llm,
                observability=hub,
                trace_id=session.trace_id,
                run_id=session.run_id,
                bindings=bindings,
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
