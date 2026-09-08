"""Thin RunLoopDriver adapter that hangs agent_lab InfoEdge onto LCA.

Registers ``run_loop_driver_registry[infoedge]``. Execute injects the
RunSession's existing Session via ``configure_session`` and calls
``agent_lab.runtime.runner``; it does not create ``agent_lab_default``,
does not call ``agent_lab.run._bootstrap()``, and does not read secrets
from the environment.

MVP execute graph is ``event_log``: it exercises the runner and the
session_log emitter without LLM or Gateway. Absorb target remains
``agent_loop`` (InfoEdge tree into CompiledRunPlan).

# COMPAT(owner: agent_lab absorb / ADR-0206; delete-when:
#   InfoEdgeSpec in CompiledRunPlan + GenericPlanInterpreter recursive
#   nested subgraphs + rg 'agent_lab.runtime.runner' lca/ profiles/ bundles/ = 0)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.transport.webserver.carrier.runs.execute.loop_drivers import DriverOutcome

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.models.team.run.context import RunContext
    from lca.infrastructure.observability import BoundObservability
    from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
        RunSession,
    )

_log = structlog.get_logger(__name__)

# MVP runnable graph (runner + session emitter, no LLM). Absorb target is agent_loop.
_MVP_GRAPH_ID = "event_log"
_AGENT_LOOP_SUBS = (
    "perceive",
    "model_eye",
    "act",
    "agent_loop",
    "think",
    "reflect",
    "remember",
)


class Config(BaseModel):
    """Pydantic config for ``lca-loop-infoedge``."""

    model_config = ConfigDict(extra="forbid")
    target: str = "infoedge"


def _resolve_injected_session(session: object) -> object:
    """Return the Session hung on ``RunSession.event_session``.

    Fail loud when the slot is missing or has no ``append``. Do not
    construct ``Session(session_id='agent_lab_default')``.
    """
    bound = getattr(session, "event_session", None)
    if bound is None:
        raise RuntimeError(
            "infoedge driver requires RunSession.event_session; "
            "refusing to create session_id=agent_lab_default"
        )
    bridge = getattr(bound, "bridge", None)
    inner = getattr(bridge, "inner", None) if bridge is not None else None
    if callable(getattr(inner, "append", None)):
        return inner
    if callable(getattr(bound, "append", None)):
        return bound
    raise RuntimeError(
        f"infoedge driver: event_session {type(bound).__name__} has no Session.append"
    )


def _initial_artifacts(question: str) -> dict[str, Any]:
    """Build the smallest artifact map the MVP graph plus agent_loop accept."""
    from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_message, make_text

    text = question.strip() if isinstance(question, str) else ""
    if not text:
        text = "infoedge"
    return {
        "event_type": make_text("graph.user_turn.v1"),
        "event_data": Artifact(
            kind=ArtifactKind.FACT,
            content={"text": text},
            schema_ref="event.data.v1",
        ),
        "user_turn": make_message("user", text, tool_calls=[]),
        "system": make_text("you are a careful assistant", schema_ref="system.v1"),
        "history": Artifact(kind=ArtifactKind.MESSAGE, content=[], schema_ref="openai.messages.v1"),
        "state": Artifact(
            kind=ArtifactKind.FACT,
            content={"trace_id": "infoedge", "task": text, "step": 0},
            schema_ref="agent.state.v1",
        ),
        "results": Artifact(kind=ArtifactKind.TEXT, content=""),
    }


class InfoEdgeRunDriver:
    """RunLoopDriver that delegates to ``agent_lab.runtime.runner``."""

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: BoundObservability,
        bindings: Any,
        run_context: RunContext,
        ctx: Context,
        machine_resolver: Any | None = None,
    ) -> DriverOutcome:
        del mode, hub, bindings, run_context, ctx, machine_resolver
        from agent_lab.graphs import load_registry
        from agent_lab.nodes.session_log._sink import configure_session
        from agent_lab.runtime.runner import run as run_graph
        from lca.plugins.lab.internal.loader import load_all

        event_session = _resolve_injected_session(session)
        configure_session(event_session)
        load_all()
        try:
            specs = load_registry(_MVP_GRAPH_ID, *_AGENT_LOOP_SUBS)
            spec = specs[_MVP_GRAPH_ID]
            trace = run_graph(
                spec,
                initial=_initial_artifacts(question),
                sub_registry=specs,
            )
        except Exception as exc:
            _log.warning("infoedge_driver_failed", error=str(exc))
            return DriverOutcome(success=False, error=str(exc))
        summary = {
            "graph": spec.id,
            "trace_events": len(trace.events),
            "artifact_keys": sorted(trace.final_artifacts),
        }
        return DriverOutcome(success=True, result=summary)


def _infoedge_driver_factory() -> InfoEdgeRunDriver:
    return InfoEdgeRunDriver()


@plugin(
    id="lca-loop-infoedge",
    Config=Config,
    requires=["run_loop_driver_registry"],
    provides=["run_loop_driver_registry[infoedge]"],
    implements=[],
    layer="L4",
    effects="none",
    description="Register the agent_lab InfoEdge RunLoopDriver adapter.",
    test_suite="tests/plugins/loop/driver/test_infoedge_driver.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Mount the InfoEdge run driver on the profile's driver registry."""
    registry = ctx.require("run_loop_driver_registry")
    registry.register(config.target, _infoedge_driver_factory)
    _log.debug("infoedge_run_driver_registered", target=config.target)


__all__ = ["Config", "InfoEdgeRunDriver", "setup"]
