"""PerceiveHub — the sole ``ContextManifested`` emitter (PR3a / v3 §3.5).

Combines ``Memory.perceive`` with a list of Sensors into a single
``ContextManifest`` per step.  The fold order is fixed (per spec §5.5):

    sensors (composition order) → Budgeter → Memory adapter → GateDecided
    fold → ContextManifested emit

Sensors failures are isolated: a single bad sensor does not poison the
manifest.  The Hub does NOT mutate ``state.history`` or
``state.working_memory`` directly — the Reasoner never reads
working_memory for world facts.

The Hub's outputs are written to two typed slots on AgentState:

- ``state.current_manifest`` (typed) → readable by the Reasoner
- ``state.gate_decided`` (typed bucket) → drained on each fold
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from lca.cognition.brain.context_manifest import (
    build_manifest_from_items,
    digest_manifest,
)
from lca.cognition.perceive_sink import ManifestSink, default_sink
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.diagnostic import DiagnosticCategory, DiagnosticStatus
from lca.contracts.protocols import MemorySystem, PerceiveHub, Sensor
from lca.contracts.protocols.think.cognition import SensorDisabledError
from lca.infrastructure.observability import record_runtime

_log = structlog.get_logger("lca.perceive_hub")


class SequentialPerceiveHub(PerceiveHub):
    """Default Hub: composition order, no fan-out.

    The Hub is the SOLE emitter of ``ContextManifested`` (PR2).  The
    result is a pure ``ContextManifest`` so the Reasoner can render its
    prompt strictly from this object.
    """

    def __init__(
        self,
        sensors: Sequence[Sensor],
        memory: MemorySystem | None,
        *,
        sink: ManifestSink | None = None,
    ) -> None:
        self._sensors = list(sensors)
        self._memory = memory
        self._sink: ManifestSink = sink if sink is not None else default_sink()

    async def perceive(self, state: AgentState) -> ContextManifest:
        # ADR-0164 Phase 3: 开 perceive step + close 围绕 _fold + emit。
        # 所有 bridge 调用都被 ``observability_firewall`` 接住:
        # schema 漂移(AttributeError / TypeError) 不再打死主链路,
        # 直接以 RuntimeObserved 写入 journal, 现场立刻可见。
        from lca.runtime.observability_firewall import bridge_firewall
        from lca.runtime.step_emitter import (
            bridge_perceive_closed,
            bridge_perceive_opened,
        )

        # AgentState 的字段名契约是 ``task``(不是 ``objective``); 用 getattr
        # 安全读取避免字段漂移。 ``objective`` 是 step-tree 的 StepContext 字段,
        # 这里把 task 映射为 step objective 是语义正确的连接。
        step_objective = getattr(state, "task", "") or "perceive"
        with bridge_firewall("bridge.perceive_opened", attributes={"step": state.step}):
            bridge_perceive_opened(objective=str(step_objective))

        items = await self._fold(state)
        manifest = build_manifest_from_items(items)
        # Write the typed slot — the Reasoner reads this.
        view = PerceiveState.from_agent_state(state)
        view.current_manifest = manifest
        view.commit(state)
        # Emit the journal event through the typed sink.
        from lca.contracts.models.observability.journal import ContextManifested

        event = ContextManifested(
            step=state.step,
            item_kinds=tuple(item.kind for item in items),
            digest=digest_manifest(manifest),
            item_refs=(),
            persist_full_prompt=False,
        )
        self._sink.emit(event, manifest)

        # close perceive step(默认 ok, 失败由 _fold 内部异常上抛, bridge 不接管)
        kinds = ", ".join(item.kind for item in items)
        with bridge_firewall(
            "bridge.perceive_closed",
            attributes={"step": state.step, "item_count": len(items)},
        ):
            bridge_perceive_closed(
                outcome="ok",
                summary=f"感知 {len(items)} 项 ({kinds})",
            )
        return manifest

    async def _fold(self, state: AgentState) -> list[ContextItem]:
        items: list[ContextItem] = []

        # 1. Sensors (composition order; failures isolated).
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
                record_runtime(
                    DiagnosticCategory.PLUGIN,
                    "sensor.read",
                    plugin=type(sensor).__name__,
                    attributes={"step": state.step},
                    output={"error": str(exc)},
                    status=DiagnosticStatus.FAILED,
                )
                continue

        # 2. Memory adapter (per spec §5.5): consume its returned state value.
        if self._memory is not None:
            try:
                memory_state = await self._memory.perceive(state)
                items.extend(_memory_items(memory_state))
            except Exception as exc:
                _log.warning("memory_perceive_failed", error=str(exc))
                record_runtime(
                    DiagnosticCategory.MEMORY,
                    "memory.perceive",
                    plugin=type(self._memory).__name__,
                    attributes={"step": state.step},
                    output={"error": str(exc)},
                    status=DiagnosticStatus.FAILED,
                )

        # 3. GateDecided fold (PR4): PolicyFacts from the previous step's
        # gate decisions.  The Reasoner never reads state.working_memory
        # for these — they reach the prompt via the manifest.
        items.extend(_gate_decided_items(state))

        return items


def _memory_items(state: AgentState) -> list[ContextItem]:
    """Fold the memory protocol's returned retrieval context into one item."""
    if not state.retrieved_context:
        return []
    return [
        ContextItem(
            kind="memory",
            payload=list(state.retrieved_context),
            provenance="memory.perceive",
        )
    ]


def _gate_decided_items(state: AgentState) -> list[ContextItem]:
    """Fold the typed ``gate_decided`` bucket into PolicyFacts.

    The bucket is drained on read so the next step starts fresh.  This
    makes the fold equivalent to a journal ``apply_delta`` for this
    slice of state.
    """
    view = PerceiveState.from_agent_state(state)
    if not view.gate_decided:
        return []
    items: list[ContextItem] = []
    for event in view.gate_decided:
        if not isinstance(event, GateDecided):
            continue
        if event.policy_fact is None:
            continue
        items.append(
            ContextItem(
                kind="policy_fact",
                payload=event.policy_fact.message,
                provenance=event.policy_fact.source,
                extra={"kind": event.policy_fact.kind, "gate": event.gate},
            )
        )
    view.gate_decided = []
    view.commit(state)
    return items
