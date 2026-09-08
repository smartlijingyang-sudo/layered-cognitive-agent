"""Adapter: agent_lab perceive.sub_spec ↔ LCA PerceiveHub production path.

Mirrors ``SequentialPerceiveHub._fold`` step ownership:
  resolve sensors+memory → sense.read → memory.perceive → policy facts → trim → commit.

Providers keep node.config JSON-serializable (fixture / factory / default).
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

_FIXTURE_SENSORS: dict[str, list[Any]] = {}
_FIXTURE_MEMORIES: dict[str, Any] = {}


def register_fixture_sensors(name: str, sensors: list[Any]) -> None:
    _FIXTURE_SENSORS[name] = list(sensors)


def unregister_fixture_sensors(name: str) -> None:
    _FIXTURE_SENSORS.pop(name, None)


def register_fixture_memory(name: str, memory: Any) -> None:
    _FIXTURE_MEMORIES[name] = memory


def unregister_fixture_memory(name: str) -> None:
    _FIXTURE_MEMORIES.pop(name, None)


@dataclass(frozen=True)
class LcaPerceiveResolveProvider:
    """Resolve Sensor list + MemorySystem for the Hub fold chain."""

    _sensors: tuple[Any, ...]
    _memory: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaPerceiveResolveProvider:
        cfg = config.get("provider_config") or {}
        sensors_name = cfg.get("fixture_sensors_name")
        if sensors_name and sensors_name in _FIXTURE_SENSORS:
            sensors: list[Any] = list(_FIXTURE_SENSORS[sensors_name])
        else:
            sensors = _default_sensors(cfg)

        mem_name = cfg.get("fixture_memory_name")
        if mem_name and mem_name in _FIXTURE_MEMORIES:
            memory = _FIXTURE_MEMORIES[mem_name]
        else:
            memory = _default_memory(cfg)
        return cls(_sensors=tuple(sensors), _memory=memory)

    def resolve(self) -> dict[str, Artifact]:
        return {
            "sensors": Artifact(
                kind=ArtifactKind.FACT,
                content={"sensors": list(self._sensors)},
                schema_ref="perceive.sensors.v1",
            ),
            "memory_ref": Artifact(
                kind=ArtifactKind.FACT,
                content=self._memory,
                schema_ref="memory.system.v1",
            ),
        }


def fold_sensor_items(
    *, sensors_artifact: Artifact | None, state_artifact: Artifact | None
) -> dict[str, Artifact]:
    """Call Sensor.read(state) for each resolved sensor (Hub sense step)."""
    state = coerce_agent_state(state_artifact)
    sensors = _sensors_from_artifact(sensors_artifact)
    items: list[dict[str, Any]] = []
    for sensor in sensors:
        try:
            raw = _run_async(sensor.read(state))
        except Exception:
            raw = []
        items.extend(context_item_to_dict(it) for it in (raw or []))
    return {
        "sensor_items": Artifact(
            kind=ArtifactKind.FACT,
            content={"items": items},
            schema_ref="context.items.v1",
        )
    }


def fold_memory_items(
    *, memory_artifact: Artifact | None, state_artifact: Artifact | None
) -> dict[str, Artifact]:
    """Call MemorySystem.perceive(state) and project retrieved_context items."""
    state = coerce_agent_state(state_artifact)
    memory = memory_artifact.content if memory_artifact is not None else None
    items: list[dict[str, Any]] = []
    if memory is not None and hasattr(memory, "perceive"):
        try:
            memory_state = _run_async(memory.perceive(state))
            retrieved = getattr(memory_state, "retrieved_context", None) or []
            if retrieved:
                items.append(
                    {
                        "kind": "memory",
                        "payload": list(retrieved),
                        "provenance": "memory.perceive",
                    }
                )
        except Exception:
            items = []
    return {
        "memory_items": Artifact(
            kind=ArtifactKind.FACT,
            content={"items": items},
            schema_ref="context.items.v1",
        )
    }


def fold_policy_items(*, state_artifact: Artifact | None) -> dict[str, Artifact]:
    """Fold prior-step GateDecided policy facts from Session (Hub policy step)."""
    from lca.contracts.harness.fold.perceive import fold_gate_decisions_from_events
    from lca.contracts.models.core.perceive.perception import ContextItem
    from lca.infrastructure.session._overflow_0.bindings import resolve_session_reader

    state = coerce_agent_state(state_artifact)
    items: list[dict[str, Any]] = []
    try:
        session = resolve_session_reader()
        prior_step = int(getattr(state, "step", 0) or 0) - 1
        if session is not None and prior_step >= 0:
            decisions = fold_gate_decisions_from_events(
                session.snapshot_events(),
                step=prior_step,
            )
            for event in decisions:
                fact = getattr(event, "policy_fact", None)
                if fact is None:
                    continue
                items.append(
                    context_item_to_dict(
                        ContextItem(
                            kind="policy_fact",
                            payload=fact.message,
                            provenance=fact.source,
                            extra={"kind": fact.kind, "gate": event.gate},
                        )
                    )
                )
    except Exception:
        items = []
    return {
        "policy_items": Artifact(
            kind=ArtifactKind.FACT,
            content={"items": items},
            schema_ref="context.items.v1",
        )
    }


def trim_items(
    *,
    sensor_items: Artifact | None,
    memory_items: Artifact | None,
    policy_items: Artifact | None,
    max_chars: int | None = None,
) -> dict[str, Artifact]:
    """Concatenate Hub item streams and apply ContextBudgeter.trim."""
    from lca.contracts.harness.state.context_budget import (
        DEFAULT_CONTEXT_BUDGET_CHARS,
        ContextBudgeter,
    )

    merged = _items_list(sensor_items) + _items_list(memory_items) + _items_list(policy_items)
    typed = [context_item_from_dict(raw) for raw in merged if raw.get("kind")]
    budget = ContextBudgeter(max_chars or DEFAULT_CONTEXT_BUDGET_CHARS)
    trimmed = budget.trim(tuple(typed))
    return {
        "trimmed_items": Artifact(
            kind=ArtifactKind.FACT,
            content={"items": [context_item_to_dict(it) for it in trimmed]},
            schema_ref="context.items.v1",
        )
    }


def commit_manifest(*, trimmed_items: Artifact | None) -> dict[str, Artifact]:
    """Build ContextManifest + digest (Hub commit step; no Session write)."""
    from lca.cognition.brain.pipeline.context_manifest import (
        build_manifest_from_items,
        digest_manifest,
    )

    items = [context_item_from_dict(raw) for raw in _items_list(trimmed_items) if raw.get("kind")]
    manifest = build_manifest_from_items(items)
    digest = digest_manifest(manifest)
    return {
        "context_manifest": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "items": [context_item_to_dict(it) for it in manifest.items],
                "digest": digest,
                "schema_version": getattr(manifest, "schema_version", "1.0"),
            },
            schema_ref="context.manifest.v1",
        )
    }


def coerce_agent_state(state_artifact: Artifact | None) -> Any:
    """Build a minimal AgentState from an artifact dict (or empty sentinel)."""
    from lca.contracts.models.core.state.state import AgentState, Budget

    content = state_artifact.content if state_artifact is not None else None
    if isinstance(content, AgentState):
        return content
    data = content if isinstance(content, dict) else {}
    budget = data.get("budget")
    if not isinstance(budget, Budget):
        budget = Budget()
    return AgentState(
        trace_id=str(data.get("trace_id") or ""),
        task=str(data.get("task") or ""),
        budget=budget,
        step=int(data.get("step") or 0),
        retrieved_context=list(data.get("retrieved_context") or []),
        extra=dict(data.get("extra") or {}),
    )


def context_item_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    return {
        "kind": getattr(item, "kind", ""),
        "payload": getattr(item, "payload", None),
        "provenance": getattr(item, "provenance", ""),
        "ref": getattr(item, "ref", None),
        "extra": dict(getattr(item, "extra", {}) or {}),
    }


def context_item_from_dict(raw: dict[str, Any]) -> Any:
    from lca.contracts.models.core.perceive.perception import ContextItem

    return ContextItem(
        kind=raw.get("kind") or "clock",
        payload=raw.get("payload"),
        provenance=str(raw.get("provenance") or ""),
        ref=raw.get("ref"),
        extra=dict(raw.get("extra") or {}),
    )


def _default_sensors(cfg: dict[str, Any]) -> list[Any]:
    factory = cfg.get("sensors_factory")
    if isinstance(factory, dict) and factory.get("ref"):
        built = _import_dotted(factory["ref"])
        kwargs = dict(factory.get("kwargs") or {})
        result = built(**kwargs) if callable(built) else built
        return list(result) if isinstance(result, (list, tuple)) else [result]
    from lca.cognition.sensors.clock import ClockSensor

    return [ClockSensor()]


def _default_memory(cfg: dict[str, Any]) -> Any:
    factory = cfg.get("memory_factory")
    if isinstance(factory, dict) and factory.get("ref"):
        mem_cls = _import_dotted(factory["ref"])
        kwargs = dict(factory.get("kwargs") or {})
        return mem_cls(**kwargs)
    return _NoopMemory()


class _NoopMemory:
    """Default memory: perceive returns state unchanged (no journal side effects)."""

    async def perceive(self, state: Any) -> Any:
        return state

    async def update(self, state: Any, observation: Any, reflection: Any) -> None:
        return None

    def query(self, layer: Any) -> list:
        return []


def _sensors_from_artifact(artifact: Artifact | None) -> list[Any]:
    if artifact is None:
        return []
    content = artifact.content
    if isinstance(content, dict):
        sensors = content.get("sensors", [])
        return list(sensors) if isinstance(sensors, list) else []
    if isinstance(content, list):
        return list(content)
    return []


def _items_list(artifact: Artifact | None) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    content = artifact.content
    if isinstance(content, dict):
        items = content.get("items", [])
        return [dict(x) for x in items if isinstance(x, dict)] if isinstance(items, list) else []
    if isinstance(content, list):
        return [dict(x) for x in content if isinstance(x, dict)]
    return []


def _import_dotted(ref: str) -> Any:
    if ":" in ref:
        mod, _, attr = ref.partition(":")
        obj = importlib.import_module(mod)
        return getattr(obj, attr)
    return importlib.import_module(ref)


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    try:
        import nest_asyncio  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "LcaPerceive* called inside a running event loop; "
            "install nest_asyncio or invoke node.execute() outside a loop"
        ) from exc
    nest_asyncio.apply()
    return asyncio.run(coro)


__all__ = [
    "LcaPerceiveResolveProvider",
    "coerce_agent_state",
    "commit_manifest",
    "context_item_from_dict",
    "context_item_to_dict",
    "fold_memory_items",
    "fold_policy_items",
    "fold_sensor_items",
    "register_fixture_memory",
    "register_fixture_sensors",
    "trim_items",
    "unregister_fixture_memory",
    "unregister_fixture_sensors",
]
