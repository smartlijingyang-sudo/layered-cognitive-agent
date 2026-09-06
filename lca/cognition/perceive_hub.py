"""PerceiveHub — fold sensors + memory + gate policy facts into ContextManifest."""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from lca.cognition.brain.context_manifest import build_manifest_from_items, digest_manifest
from lca.cognition.perceive_sink import ManifestSink
from lca.contracts.harness.fold.perceive import fold_gate_decisions_from_events
from lca.contracts.harness.state.context_budget import (
    DEFAULT_CONTEXT_BUDGET_CHARS,
    ContextBudgeter,
)
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.diagnostic import DiagnosticCategory, DiagnosticStatus
from lca.contracts.protocols import MemorySystem, PerceiveHub, Sensor
from lca.contracts.protocols.think.cognition import SensorDisabledError
from lca.infrastructure.session.bindings import resolve_session_reader
from lca.infrastructure.session.fact_committer import emit_diagnostic

_log = structlog.get_logger("lca.perceive_hub")


class SequentialPerceiveHub(PerceiveHub):
    """Default Hub: composition order, no fan-out, no fact I/O (ADR-0192)."""

    def __init__(
        self,
        sensors: Sequence[Sensor],
        memory: MemorySystem | None,
        *,
        sink: ManifestSink | None = None,
        max_context_chars: int = DEFAULT_CONTEXT_BUDGET_CHARS,
    ) -> None:
        del sink  # COMPAT(ADR-0192 E4): JournalSink ignored; facts via PhaseFactEmitter
        self._sensors = list(sensors)
        self._memory = memory
        self._budgeter = ContextBudgeter(max_context_chars)

    async def perceive(self, state: AgentState) -> ContextManifest:
        items = await self._fold(state)
        digest = digest_manifest(build_manifest_from_items(items))
        return ContextManifest(items=tuple(items), digest=digest)

    async def _fold(self, state: AgentState) -> list[ContextItem]:
        items: list[ContextItem] = []

        for sensor in self._sensors:
            try:
                items.extend(await sensor.read(state))
            except SensorDisabledError:
                continue
            except Exception as exc:
                _log.warning(
                    "sensor_failed",
                    sensor=type(sensor).__name__,
                    error=str(exc),
                )
                emit_diagnostic(
                    category=DiagnosticCategory.PLUGIN.value,
                    operation="sensor.read",
                    plugin=type(sensor).__name__,
                    attributes={"step": state.step},
                    output={"error": str(exc)},
                    status=DiagnosticStatus.FAILED.value,
                )
                continue

        if self._memory is not None:
            try:
                memory_state = await self._memory.perceive(state)
                items.extend(_memory_items(memory_state))
            except Exception as exc:
                _log.warning("memory_perceive_failed", error=str(exc))
                emit_diagnostic(
                    category=DiagnosticCategory.MEMORY.value,
                    operation="memory.perceive",
                    plugin=type(self._memory).__name__,
                    attributes={"step": state.step},
                    output={"error": str(exc)},
                    status=DiagnosticStatus.FAILED.value,
                )

        items.extend(_policy_fact_items(state))
        return list(self._budgeter.trim(tuple(items)))


def _memory_items(state: AgentState) -> list[ContextItem]:
    if not state.retrieved_context:
        return []
    return [
        ContextItem(
            kind="memory",
            payload=list(state.retrieved_context),
            provenance="memory.perceive",
        )
    ]


def _policy_fact_items(state: AgentState) -> list[ContextItem]:
    session = resolve_session_reader()
    if session is not None:
        prior_step = state.step - 1
        if prior_step >= 0:
            decisions = fold_gate_decisions_from_events(
                session.snapshot_events(),
                step=prior_step,
            )
            if decisions:
                _drain_gate_decided_bucket(state)
                return [_policy_fact_item(event) for event in decisions if event.policy_fact]
    return _policy_fact_items_from_bucket(state)


def _policy_fact_items_from_bucket(state: AgentState) -> list[ContextItem]:
    view = PerceiveState.from_agent_state(state)
    if not view.gate_decided:
        return []
    items: list[ContextItem] = []
    for event in view.gate_decided:
        if not isinstance(event, GateDecided):
            continue
        if event.policy_fact is None:
            continue
        items.append(_policy_fact_item(event))
    view.gate_decided = []
    view.commit(state)
    return items


def _drain_gate_decided_bucket(state: AgentState) -> None:
    view = PerceiveState.from_agent_state(state)
    if not view.gate_decided:
        return
    view.gate_decided = []
    view.commit(state)


def _policy_fact_item(event: GateDecided) -> ContextItem:
    fact = event.policy_fact
    if fact is None:
        raise ValueError("policy_fact_item requires GateDecided.policy_fact")
    return ContextItem(
        kind="policy_fact",
        payload=fact.message,
        provenance=fact.source,
        extra={"kind": fact.kind, "gate": event.gate},
    )


__all__ = ["SequentialPerceiveHub"]
