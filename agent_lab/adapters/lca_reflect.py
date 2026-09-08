"""Adapter: agent_lab reflect.critique ↔ LCA Critic.

LCA contracts consumed (read-only):
  - lca.contracts.protocols.think.cognition.Critic
  - lca.contracts.models.core.execution.decision.Observation, Reflection
  - lca.contracts.models.core.state.state.AgentState

agent_lab provides (this file):
  - LcaReflectCriticProvider: wraps a Critic and exposes .critique() that
    takes a combined artifact (observation + decision) and returns a
    Reflection artifact for ``reflect.critique``.

Reflect does not own durable memory writes. ``LcaReflectMemoryProvider``
remains for remember-phase wiring only; ``reflect.extract`` emits
candidates without calling MemorySystem.update.

Critic choice: LCA ships ``SimpleCritic`` (heuristic) and ``NullCritic``
(no-op).  Default is ``NullCritic`` (ON_TRACK, no lesson) because
SimpleCritic needs a live AgentState with history. Override with
``fixture_critic_name`` in tests or ``critic_factory`` in profiles.
"""

from __future__ import annotations

import asyncio
import importlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

# ---------------------------------------------------------------------------
# Shared: process-local fixture registries
# ---------------------------------------------------------------------------
_FIXTURE_CRITICS: dict[str, Any] = {}
_FIXTURE_MEMORIES: dict[str, Any] = {}


def register_fixture_critic(name: str, critic: Any) -> None:
    _FIXTURE_CRITICS[name] = critic


def unregister_fixture_critic(name: str) -> None:
    _FIXTURE_CRITICS.pop(name, None)


def register_fixture_memory(name: str, mem: Any) -> None:
    _FIXTURE_MEMORIES[name] = mem


def unregister_fixture_memory(name: str) -> None:
    _FIXTURE_MEMORIES.pop(name, None)


# ---------------------------------------------------------------------------
# Critic provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaReflectCriticProvider:
    """Bridge reflect.critique → LCA Critic.critique().

    Resolution order for the critic:
      1. ``provider_config.fixture_critic_name`` (looks up ``_FIXTURE_CRITICS``)
      2. ``provider_config.critic_factory`` (module:Class form)
      3. Fallback: ``NullCritic`` (returns ON_TRACK, no lesson)
    """

    _critic: Any  # lca.contracts.protocols.Critic; late-bound

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaReflectCriticProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_critic_name")
        if name and name in _FIXTURE_CRITICS:
            return cls(_critic=_FIXTURE_CRITICS[name])
        factory = cfg.get("critic_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            critic_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_critic=critic_cls(**kwargs))
        # Fallback: NullCritic (always returns ON_TRACK, no lesson).
        return cls(_critic=_stub_critic())

    def critique(
        self,
        *,
        combined_artifact: Artifact | None,
    ) -> dict[str, Artifact]:
        combined = combined_artifact.content if combined_artifact else {}
        if not isinstance(combined, dict):
            combined = {}
        observation_dict = combined.get("in_observation") or {}
        if not isinstance(observation_dict, dict):
            observation_dict = {}
        observation = _observation_from_dict(observation_dict)
        state = _coerce_state(combined.get("in_decision"))
        reflection = _run_async(self._critic.critique(state=state, observation=observation))
        return {
            "reflection": Artifact(
                kind=ArtifactKind.FACT,
                content=_reflection_to_dict(reflection),
                schema_ref="reflection.v1",
            ),
        }


# ---------------------------------------------------------------------------
# Memory provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaReflectMemoryProvider:
    """Bridge remember-phase memory write → LCA MemorySystem.update().

    Not used by reflect (candidates only). Resolution order:
      1. ``provider_config.fixture_memory_name`` (looks up ``_FIXTURE_MEMORIES``)
      2. ``provider_config.memory_factory`` (module:Class form)
      3. Fallback: ``_StubMemorySystem`` (records call, no-op)
    """

    _memory: Any  # lca.contracts.protocols.MemorySystem; late-bound

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaReflectMemoryProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_memory_name")
        if name and name in _FIXTURE_MEMORIES:
            return cls(_memory=_FIXTURE_MEMORIES[name])
        factory = cfg.get("memory_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            mem_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_memory=mem_cls(**kwargs))
        # Fallback: stub memory (records call, no-op).
        return cls(_memory=_StubMemorySystem())

    def write(
        self,
        *,
        reflection_artifact: Artifact | None,
        memory_artifact: Artifact | None,
    ) -> dict[str, Artifact]:
        reflection_dict = reflection_artifact.content if reflection_artifact else {}
        if not isinstance(reflection_dict, dict):
            reflection_dict = {}
        memory_dict = memory_artifact.content if memory_artifact else {}
        if not isinstance(memory_dict, dict):
            memory_dict = {}

        reflection = _reflection_from_dict(reflection_dict)
        observation = _observation_from_dict({})
        state = _coerce_state(None)
        _run_async(self._memory.update(state=state, observation=observation, reflection=reflection))

        return {
            "reflection_out": Artifact(
                kind=ArtifactKind.FACT,
                content=reflection_dict,
                schema_ref="reflection.v1",
            ),
            "memory_extract_out": Artifact(
                kind=ArtifactKind.FACT,
                content=memory_dict,
                schema_ref="memory.candidates.v1",
            ),
            "reflect_signal": Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "reflection_id": reflection_dict.get("reflection_id", ""),
                    "verdict": reflection_dict.get("verdict", ""),
                    "ts": datetime.now(UTC).isoformat(),
                },
                schema_ref="reflect.signal.v1",
            ),
        }


# ---------------------------------------------------------------------------
# Defaults / stubs
# ---------------------------------------------------------------------------


def _stub_critic() -> Any:
    """Return a NullCritic — always returns ON_TRACK, no lesson."""
    try:
        from lca.cognition.brain.reasoner.null_critic import NullCritic

        return NullCritic()
    except Exception:
        return _StubCritic()


class _StubCritic:
    """Minimal Critic when LCA's NullCritic is unavailable."""

    async def critique(self, state: Any, observation: Any) -> Any:
        from lca.contracts.atoms.enums.enums import ReflectionVerdict
        from lca.contracts.atoms.ids.ids import new_id
        from lca.contracts.models.core.execution.decision import Reflection

        return Reflection(
            reflection_id=new_id("refl"),
            verdict=ReflectionVerdict.ON_TRACK,
            lesson=None,
        )


class _StubMemorySystem:
    """No-op MemorySystem that records calls for test inspection."""

    def __init__(self) -> None:
        object.__setattr__(self, "calls", [])

    async def perceive(self, state: Any) -> Any:
        return state

    async def update(self, state: Any, observation: Any, reflection: Any) -> None:
        self.calls.append({"state": state, "observation": observation, "reflection": reflection})

    def query(self, layer: Any) -> list:
        return []


# ---------------------------------------------------------------------------
# Helpers — artifact ⇄ LCA dataclass conversions
# ---------------------------------------------------------------------------


def _observation_from_dict(d: dict[str, Any]) -> Any:
    from lca.contracts.models.core.execution.decision import Observation

    return Observation(
        observation_id=str(d.get("observation_id") or f"obs_{uuid.uuid4().hex[:12]}"),
        success=bool(d.get("success", True)),
        payload=d.get("payload"),
        error=d.get("error"),
        extra=dict(d.get("extra") or {}),
    )


def _verdict_str(verdict: Any) -> str:
    """Extract the string value from a ReflectionVerdict enum or plain str."""
    if hasattr(verdict, "value"):
        return str(verdict.value)
    return str(verdict)


def _reflection_to_dict(reflection: Any) -> dict[str, Any]:
    from lca.contracts.models.core.execution.decision import Decision

    correction = getattr(reflection, "correction", None)
    correction_dict = None
    if correction is not None and isinstance(correction, Decision):
        correction_dict = {
            "decision_id": getattr(correction, "decision_id", ""),
            "action_type": getattr(correction, "action_type", ""),
            "rationale": getattr(correction, "rationale", "") or "",
        }
    return {
        "reflection_id": getattr(reflection, "reflection_id", ""),
        "verdict": _verdict_str(getattr(reflection, "verdict", "on_track")),
        "lesson": getattr(reflection, "lesson", None),
        "correction": correction_dict,
        "extra": dict(getattr(reflection, "extra", {}) or {}),
    }


def _reflection_from_dict(d: dict[str, Any]) -> Any:
    from lca.contracts.atoms.enums.enums import ReflectionVerdict
    from lca.contracts.atoms.ids.ids import new_id
    from lca.contracts.models.core.execution.decision import Reflection

    verdict_raw = d.get("verdict", "on_track")
    try:
        verdict = ReflectionVerdict(verdict_raw)
    except ValueError:
        verdict = ReflectionVerdict.ON_TRACK
    return Reflection(
        reflection_id=str(d.get("reflection_id") or new_id("refl")),
        verdict=verdict,
        lesson=d.get("lesson"),
        extra=dict(d.get("extra") or {}),
    )


def _coerce_state(decision_content: Any) -> Any:
    """Coerce a decision artifact content into a minimal LCA AgentState.

    AgentState is a frozen dataclass with required positional fields.
    We supply empty sentinels; the Critic rarely reads history anyway.
    """
    from lca.contracts.models.core.state.state import AgentState

    return AgentState(trace_id="", task="", budget=None)


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
            "LcaReflect* provider called inside a running event loop; "
            "install nest_asyncio or invoke node.execute() outside a loop"
        ) from exc
    nest_asyncio.apply()
    return asyncio.run(coro)


def _call_maybe_async(fn: Any, *args: Any) -> Any:
    """Call fn(*args); if it returns a coroutine, drive it to completion."""
    result = fn(*args)
    import inspect as _inspect

    if _inspect.isawaitable(result):
        return _run_async(result)
    return result


__all__ = [
    "LcaReflectCriticProvider",
    "LcaReflectMemoryProvider",
    "register_fixture_critic",
    "register_fixture_memory",
    "unregister_fixture_critic",
    "unregister_fixture_memory",
]
