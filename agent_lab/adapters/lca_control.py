"""Adapter: agent_lab control-slot sub-graphs ↔ LCA control protocols.

Five providers, one per ControlSlot:

  - LcaControlDecisionGateProvider   — wraps DecisionGate (think_guard)
  - LcaControlStopPolicyProvider     — wraps StopPolicy (stop_decide)
  - LcaControlCheckpointProvider     — wraps a checkpoint emitter (observe_checkpoint)
  - LcaControlRememberAdmitProvider  — wraps a callable admit policy (remember_admit)
  - LcaControlStopFocusProvider      — focus-aware stop governance (stop.focus side-channel)

Each follows the same fixture_X_name / X_factory / fallback resolution
as ``LcaThinkGateProvider`` (see lca_think.py). Helpers are imported from
that module to avoid duplication.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Re-use helpers from lca_think
from agent_lab.adapters.lca_think import (
    _call_maybe_async,
    _decision_from_dict,
    _decision_to_dict,
    _import_dotted,
    _run_async,
)
from agent_lab.primitives.artifact import Artifact, ArtifactKind

# ---------------------------------------------------------------------------
# Fixture registries
# ---------------------------------------------------------------------------
_FIXTURE_DECISION_GATES: dict[str, Any] = {}
_FIXTURE_STOP_POLICIES: dict[str, Any] = {}
_FIXTURE_CHECKPOINTS: dict[str, Any] = {}
_FIXTURE_REMEMBER_ADMITS: dict[str, Any] = {}
_FIXTURE_STOP_FOCUS: dict[str, Any] = {}


def register_fixture_decision_gate(name: str, gate: Any) -> None:
    _FIXTURE_DECISION_GATES[name] = gate


def unregister_fixture_decision_gate(name: str) -> None:
    _FIXTURE_DECISION_GATES.pop(name, None)


def register_fixture_stop_policy(name: str, policy: Any) -> None:
    _FIXTURE_STOP_POLICIES[name] = policy


def unregister_fixture_stop_policy(name: str) -> None:
    _FIXTURE_STOP_POLICIES.pop(name, None)


def register_fixture_checkpoint(name: str, checkpoint: Any) -> None:
    _FIXTURE_CHECKPOINTS[name] = checkpoint


def unregister_fixture_checkpoint(name: str) -> None:
    _FIXTURE_CHECKPOINTS.pop(name, None)


def register_fixture_remember_admit(name: str, admit: Any) -> None:
    _FIXTURE_REMEMBER_ADMITS[name] = admit


def unregister_fixture_remember_admit(name: str) -> None:
    _FIXTURE_REMEMBER_ADMITS.pop(name, None)


def register_fixture_stop_focus(name: str, executor: Any) -> None:
    _FIXTURE_STOP_FOCUS[name] = executor


def unregister_fixture_stop_focus(name: str) -> None:
    _FIXTURE_STOP_FOCUS.pop(name, None)


# ---------------------------------------------------------------------------
# LcaControlDecisionGateProvider — think_guard
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlDecisionGateProvider:
    """Bridge think_guard_node → LCA DecisionGate.

    Resolution order:
      1. ``provider_config.fixture_decision_gate_name``
      2. ``provider_config.gate_factory`` (module:Class form)
      3. Fallback: identity pass-through
    """

    _gate: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlDecisionGateProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_decision_gate_name")
        if name and name in _FIXTURE_DECISION_GATES:
            return cls(_gate=_FIXTURE_DECISION_GATES[name])
        factory = cfg.get("gate_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            gate_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_gate=gate_cls(**kwargs))
        return cls(_gate=_IdentityGate())

    def enforce(
        self,
        *,
        decision_artifact: Artifact | None,
        out_port: str = "out_decision",
    ) -> dict[str, Artifact]:
        decision_dict = decision_artifact.content if decision_artifact else {}
        if not isinstance(decision_dict, dict):
            decision_dict = {}
        decision = _decision_from_dict(decision_dict)
        enforced = _run_async(self._gate.enforce(state=None, decision=decision))
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content=_decision_to_dict(enforced),
                schema_ref="decision.v1",
            ),
        }


# ---------------------------------------------------------------------------
# LcaControlStopPolicyProvider — stop_decide
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlStopPolicyProvider:
    """Bridge stop_decide_node → LCA StopPolicy.decide.

    Resolution order:
      1. ``provider_config.fixture_stop_policy_name``
      2. ``provider_config.policy_factory`` (module:Class form)
      3. Fallback: _NeverStop (always returns CONTINUE)
    """

    _policy: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlStopPolicyProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_stop_policy_name")
        if name and name in _FIXTURE_STOP_POLICIES:
            return cls(_policy=_FIXTURE_STOP_POLICIES[name])
        factory = cfg.get("policy_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            policy_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_policy=policy_cls(**kwargs))
        return cls(_policy=_NeverStop())

    def decide(
        self,
        *,
        state: Any = None,
        decision: Any = None,
        observation: Any = None,
        reflection: Any = None,
        out_port: str = "stop_decision",
    ) -> dict[str, Artifact]:
        result = _call_maybe_async(self._policy.decide, state, decision, observation, reflection)
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content=_stop_decision_to_dict(result),
                schema_ref="stop_decision.v1",
            ),
        }


# ---------------------------------------------------------------------------
# LcaControlCheckpointProvider — observe_checkpoint
# ---------------------------------------------------------------------------

_checkpoint_counter = itertools.count(1)


@dataclass(frozen=True)
class LcaControlCheckpointProvider:
    """Bridge observe_checkpoint_node → checkpoint event emitter.

    Resolution order:
      1. ``provider_config.fixture_checkpoint_name``
      2. ``provider_config.checkpoint_factory`` (module:Class form)
      3. Fallback: _NoopCheckpoint (counter-stamped fact)
    """

    _emitter: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlCheckpointProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_checkpoint_name")
        if name and name in _FIXTURE_CHECKPOINTS:
            return cls(_emitter=_FIXTURE_CHECKPOINTS[name])
        factory = cfg.get("checkpoint_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            emitter_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_emitter=emitter_cls(**kwargs))
        return cls(_emitter=_NoopCheckpoint())

    def emit(
        self,
        *,
        event_type: str = "checkpoint",
        event_log: Any = None,
        out_port: str = "checkpoint_event",
    ) -> dict[str, Artifact]:
        result = _call_maybe_async(self._emitter.emit, event_type)
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content=result if isinstance(result, dict) else {"fact": str(result)},
                schema_ref="checkpoint.v1",
            ),
        }


# ---------------------------------------------------------------------------
# LcaControlRememberAdmitProvider — remember_admit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlRememberAdmitProvider:
    """Bridge remember_admit_node → callable admit policy.

    Resolution order:
      1. ``provider_config.fixture_remember_admit_name``
      2. ``provider_config.admit_factory`` (module:Class form)
      3. Fallback: _AlwaysAdmit (returns True)
    """

    _admit: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlRememberAdmitProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_remember_admit_name")
        if name and name in _FIXTURE_REMEMBER_ADMITS:
            return cls(_admit=_FIXTURE_REMEMBER_ADMITS[name])
        factory = cfg.get("admit_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            admit_fn = _import_dotted(factory["ref"])
            return cls(_admit=admit_fn)
        return cls(_admit=_AlwaysAdmit())

    def admit(
        self,
        *,
        observation: Any = None,
        out_port: str = "admit_verdict",
    ) -> dict[str, Artifact]:
        result = _call_maybe_async(self._admit, observation)
        return {
            out_port: Artifact(
                kind=ArtifactKind.VERDICT
                if hasattr(ArtifactKind, "VERDICT")
                else ArtifactKind.FACT,
                content={"admitted": bool(result)},
                schema_ref="remember_admit.v1",
            ),
        }


# ---------------------------------------------------------------------------
# Defaults / fallbacks
# ---------------------------------------------------------------------------


class _IdentityGate:
    """Pass-through gate for think_guard when no fixture/factory is configured."""

    async def enforce(self, state: Any, decision: Any) -> Any:
        return decision


class _NeverStop:
    """Fallback StopPolicy that always returns CONTINUE."""

    def decide(self, state: Any, decision: Any, observation: Any, reflection: Any) -> Any:
        from lca.contracts.models.core.policy.stop import StopDecision, StopReason

        return StopDecision(should_stop=False, reason=StopReason.CONTINUE)


class _NoopCheckpoint:
    """Fallback checkpoint emitter — counter-stamped event_fact."""

    def emit(self, event_type: str) -> dict[str, Any]:
        n = next(_checkpoint_counter)
        return {
            "event_type": event_type,
            "seq": n,
            "ts": datetime.now(UTC).isoformat(),
            "fact_id": f"ckpt_{uuid.uuid4().hex[:8]}",
        }


class _AlwaysAdmit:
    """Fallback admit policy — always admits."""

    def __call__(self, observation: Any) -> bool:
        return True


class _AlwaysFocus:
    """Fallback focus executor — always returns count=0 (allow).

    Used when no fixture / factory is configured; ensures dry runs and
    tests do not trip the focus policy unless they explicitly inject
    one. Mirrors ``FocusStopExecutor.execute`` when history is empty.
    """

    def evaluate(self, _state: Any, _decision: Any) -> dict[str, Any]:
        return {"kind": "allow", "count": 0, "limit": 0, "detail": "always-allow fallback"}


# ---------------------------------------------------------------------------
# LcaControlStopFocusProvider — stop.focus side-channel
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaControlStopFocusProvider:
    """Bridge stop_focus_node → focus-aware stop governance.

    Mirrors ``lca.plugins.loop.control.stop_focus.FocusStopExecutor``:
    counts consecutive stagnant turns (unsuccessful observation +
    reflection correction/blockage + identical intent) and returns
    a focus_verdict when the count reaches ``max_consecutive_stagnant_turns``.

    eval(state_history, decision) -> {kind: allow|stop, count: int,
    limit: int, detail: str}. Fallback: ``_AlwaysFocus`` returns
    count=0 → always allow.

    Resolution order:
      1. ``provider_config.fixture_stop_focus_name`` (looks up _FIXTURE_STOP_FOCUS)
      2. ``provider_config.stop_focus_factory`` (module:Class form)
      3. Fallback: _AlwaysFocus()
    """

    _executor: Any
    _max_consecutive_stagnant_turns: int

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaControlStopFocusProvider:
        cfg = config.get("provider_config") or {}
        limit = int(cfg.get("max_consecutive_stagnant_turns", 3) or 3)
        name = cfg.get("fixture_stop_focus_name")
        if name and name in _FIXTURE_STOP_FOCUS:
            return cls(_executor=_FIXTURE_STOP_FOCUS[name], _max_consecutive_stagnant_turns=limit)
        factory = cfg.get("stop_focus_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            exec_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_executor=exec_cls(**kwargs), _max_consecutive_stagnant_turns=limit)
        return cls(_executor=_AlwaysFocus(), _max_consecutive_stagnant_turns=limit)

    def evaluate(
        self,
        *,
        state: Any = None,
        decision: Any = None,
        out_port: str = "focus_verdict",
    ) -> dict[str, Artifact]:
        history = _extract_history(state)
        count = self._count_stagnant(history, decision)
        if count >= self._max_consecutive_stagnant_turns:
            kind = "stop"
            detail = (
                f"cognitive focus policy stopped repeated unsuccessful intent "
                f"after {count} consecutive stagnant turns "
                f"(limit={self._max_consecutive_stagnant_turns})"
            )
        else:
            kind = "allow"
            detail = (
                f"cognitive focus policy allows continuation "
                f"(consecutive_stagnant_turns={count}, "
                f"limit={self._max_consecutive_stagnant_turns})"
            )
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "kind": kind,
                    "count": count,
                    "limit": self._max_consecutive_stagnant_turns,
                    "detail": detail,
                },
                schema_ref="stop.focus.v1",
            ),
        }

    def _count_stagnant(
        self,
        history: list[dict[str, Any]],
        decision: Any,
    ) -> int:
        """Conservative stagnation counter — mirrors LCA's logic.

        A turn is stagnant only if:
          - observation.success is False
          - reflection.verdict ∈ {needs_correction, blocked}
          - decision.action_type / tool_names / response_text unchanged
            from the immediately preceding stagnant turn.

        agent_lab passes the history in via the state artifact (no
        PhaseContext); each item is a dict with optional keys
        observation, reflection, decision.
        """
        expected: tuple[Any, ...] | None = None
        count = 0
        for item in reversed(history):
            if not isinstance(item, dict):
                break
            if not _is_stagnant(item):
                break
            intent = _intent_signature(item.get("decision", decision))
            if expected is None:
                expected = intent
            elif intent != expected:
                break
            count += 1
        return count


def _extract_history(state: Any) -> list[dict[str, Any]]:
    """Pull a list-of-dicts history out of a state artifact / dict / list."""
    if state is None:
        return []
    content = getattr(state, "content", state)
    if isinstance(content, dict):
        history = content.get("history")
        if isinstance(history, list):
            return [h for h in history if isinstance(h, dict)]
        return []
    if isinstance(content, list):
        return [h for h in content if isinstance(h, dict)]
    return []


def _is_stagnant(turn: dict[str, Any]) -> bool:
    """Return whether one durable turn explicitly shows no cognitive progress."""
    observation = turn.get("observation") or {}
    reflection = turn.get("reflection") or {}
    if not isinstance(observation, dict) or not isinstance(reflection, dict):
        return False
    if observation.get("success", True):
        return False
    verdict = str(reflection.get("verdict", "")).lower()
    return verdict in {"needs_correction", "blocked"}


def _intent_signature(decision: Any) -> tuple[Any, ...]:
    """Build a conservative, deterministic identity for one declared intent."""
    if not isinstance(decision, dict):
        return ()
    action_type = str(decision.get("action_type", ""))
    tool_calls = decision.get("tool_calls") or []
    tool_names = tuple(
        str(call.get("tool_name", "") if isinstance(call, dict) else getattr(call, "tool_name", ""))
        for call in tool_calls
    )
    response = str(decision.get("response_text", "") or "").strip()
    return (action_type, tool_names, response)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stop_decision_to_dict(sd: Any) -> dict[str, Any]:
    reason = getattr(sd, "reason", None)
    reason_str = reason.value if hasattr(reason, "value") else str(reason or "continue")
    return {
        "should_stop": bool(getattr(sd, "should_stop", False)),
        "reason": reason_str,
        "final_output": getattr(sd, "final_output", None),
        "status": str(getattr(sd, "status", "") or ""),
    }


__all__ = [
    "LcaControlCheckpointProvider",
    "LcaControlDecisionGateProvider",
    "LcaControlRememberAdmitProvider",
    "LcaControlStopFocusProvider",
    "LcaControlStopPolicyProvider",
    "register_fixture_checkpoint",
    "register_fixture_decision_gate",
    "register_fixture_remember_admit",
    "register_fixture_stop_focus",
    "register_fixture_stop_policy",
    "unregister_fixture_checkpoint",
    "unregister_fixture_decision_gate",
    "unregister_fixture_remember_admit",
    "unregister_fixture_stop_focus",
    "unregister_fixture_stop_policy",
]
