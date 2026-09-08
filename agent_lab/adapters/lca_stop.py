"""Adapter: agent_lab stop sub-graph ↔ LCA StopPolicy.

LCA contracts consumed (read-only):
  - lca.contracts.models.core.policy.stop.StopDecision
  - lca.contracts.models.core.policy.stop.StopReason
  - lca.contracts.protocols.runtime.runtime.runtime.StopPolicy
  - lca.contracts.models.core.state.lifecycle.TaskStatus

agent_lab provides (this file):
  - LcaStopPolicyProvider: wraps a StopPolicy and exposes a .decide() method
    that takes four artifacts (in_decision, in_observation, in_reflection,
    in_state) and returns stop_decision + terminal artifacts.

Resolution order for the policy:
  1. ``provider_config.fixture_policy_name`` (looks up ``_FIXTURE_POLICIES``)
  2. ``provider_config.policy_factory`` (module:Class form)
  3. Fallback: ``_ContinuePolicy`` (always returns should_stop=False)
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

# ---------------------------------------------------------------------------
# Process-local fixture registry (parallels lca_think.py)
# ---------------------------------------------------------------------------
_FIXTURE_POLICIES: dict[str, Any] = {}


def register_fixture_policy(name: str, policy: Any) -> None:
    _FIXTURE_POLICIES[name] = policy


def unregister_fixture_policy(name: str) -> None:
    _FIXTURE_POLICIES.pop(name, None)


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaStopPolicyProvider:
    """Bridge agent_lab evaluate_stop node → LCA StopPolicy.

    Resolution order:
      1. ``provider_config.fixture_policy_name`` (looks up _FIXTURE_POLICIES)
      2. ``provider_config.policy_factory`` (module:Class form)
      3. Fallback: _ContinuePolicy (always returns should_stop=False)
    """

    _policy: Any  # StopPolicy-compatible

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaStopPolicyProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_policy_name")
        if name and name in _FIXTURE_POLICIES:
            return cls(_policy=_FIXTURE_POLICIES[name])
        factory = cfg.get("policy_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            policy_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_policy=policy_cls(**kwargs))
        # Fallback: always-continue policy.
        return cls(_policy=_ContinuePolicy())

    def decide(
        self,
        *,
        state_artifact: Artifact | None,
        decision_artifact: Artifact | None,
        observation_artifact: Artifact | None,
        reflection_artifact: Artifact | None,
    ) -> dict[str, Artifact]:
        state = _state_from_artifact(state_artifact)
        decision = _decision_from_artifact(decision_artifact)
        observation = _observation_from_artifact(observation_artifact)
        reflection = _reflection_from_artifact(reflection_artifact)
        stop_decision = _call_maybe_async(
            self._policy.decide, state, decision, observation, reflection
        )
        sd_dict = _stop_decision_to_dict(stop_decision)
        return {
            "stop_decision": Artifact(
                kind=ArtifactKind.FACT,
                content=sd_dict,
                schema_ref="stop_decision.v1",
            ),
            "terminal": Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "stop_decision": sd_dict,
                    "ts": datetime.now(UTC).isoformat(),
                },
                schema_ref="terminal.v1",
            ),
        }


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class _ContinuePolicy:
    """Fallback policy that always returns should_stop=False."""

    def decide(
        self,
        state: Any,
        decision: Any,
        observation: Any,
        reflection: Any,
    ) -> Any:
        from lca.contracts.models.core.policy.stop import StopDecision, StopReason

        return StopDecision(
            should_stop=False,
            reason=StopReason.CONTINUE,
            final_output=None,
            status=None,
            failure=None,
        )


# ---------------------------------------------------------------------------
# Helpers — artifact ⇄ LCA dataclass conversions
# ---------------------------------------------------------------------------


def _state_from_artifact(artifact: Artifact | None) -> Any:
    """Pass-through: state is opaque to the adapter, returned as-is from content."""
    return artifact.content if artifact else None


def _decision_from_artifact(artifact: Artifact | None) -> Any:
    """Reconstruct a Decision-like object from an Artifact."""
    if artifact is None or artifact.content is None:
        return None
    from lca.contracts.models.core.execution.decision import Decision, ToolCall

    d = artifact.content
    if not isinstance(d, dict):
        return None
    tool_calls = []
    for tc in d.get("tool_calls") or []:
        if isinstance(tc, dict):
            tool_calls.append(
                ToolCall(
                    call_id=str(tc.get("call_id") or ""),
                    tool_name=str(tc.get("name") or tc.get("tool_name") or ""),
                    arguments=dict(tc.get("arguments") or {}),
                )
            )
    return Decision(
        decision_id=str(d.get("decision_id") or ""),
        action_type=str(d.get("action_type") or "respond"),
        rationale=str(d.get("rationale") or ""),
        confidence=float(d.get("confidence") or 1.0),
        tool_calls=tool_calls,
        response_text=d.get("response_text"),
    )


def _observation_from_artifact(artifact: Artifact | None) -> Any:
    """Reconstruct an Observation-like object from an Artifact."""
    if artifact is None or artifact.content is None:
        return None
    content = artifact.content
    if isinstance(content, dict):
        return _DictNamespace(content)
    return content


def _reflection_from_artifact(artifact: Artifact | None) -> Any:
    """Reconstruct a Reflection-like object from an Artifact."""
    if artifact is None or artifact.content is None:
        return None
    content = artifact.content
    if isinstance(content, dict):
        return _DictNamespace(content)
    return content


def _stop_decision_to_dict(sd: Any) -> dict[str, Any]:
    return {
        "should_stop": bool(getattr(sd, "should_stop", False)),
        "reason": getattr(
            getattr(sd, "reason", None), "value", str(getattr(sd, "reason", "continue"))
        ),
        "final_output": getattr(sd, "final_output", None),
        "status": getattr(getattr(sd, "status", None), "value", None)
        if getattr(sd, "status", None) is not None
        else None,
        "failure": _failure_to_dict(getattr(sd, "failure", None)),
    }


def _stop_decision_from_dict(d: dict[str, Any]) -> Any:
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason
    from lca.contracts.models.core.state.lifecycle import TaskStatus, coerce_status

    reason_str = str(d.get("reason") or "continue")
    reason_map = {r.value: r for r in StopReason}
    reason = reason_map.get(reason_str, StopReason.CONTINUE)
    status = coerce_status(d.get("status"))
    return StopDecision(
        should_stop=bool(d.get("should_stop", False)),
        reason=reason,
        final_output=d.get("final_output"),
        status=status if isinstance(status, TaskStatus) else None,
        failure=None,  # RunDiagnostic reconstruction is out of scope for agent_lab
    )


def _failure_to_dict(failure: Any) -> dict[str, Any] | None:
    if failure is None:
        return None
    return {
        "run_id": getattr(failure, "run_id", ""),
        "trace_id": getattr(failure, "trace_id", ""),
        "phase": getattr(failure, "phase", ""),
        "node_id": getattr(failure, "node_id", ""),
        "error_type": getattr(failure, "error_type", ""),
        "message": getattr(failure, "message", ""),
    }


class _DictNamespace:
    """Minimal namespace wrapper so dict content supports attribute access."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None

    def __repr__(self) -> str:
        return f"_DictNamespace({self._data!r})"


def _import_dotted(ref: str) -> Any:
    if ":" in ref:
        mod, _, attr = ref.partition(":")
        obj = importlib.import_module(mod)
        return getattr(obj, attr)
    return importlib.import_module(ref)


def _call_maybe_async(fn: Any, *args: Any) -> Any:
    """Call fn(*args); if it returns a coroutine, drive it to completion."""
    result = fn(*args)
    import inspect as _inspect

    if _inspect.isawaitable(result):
        return _run_async(result)
    return result


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    try:
        import nest_asyncio  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "LcaStopPolicyProvider called inside a running event loop; "
            "install nest_asyncio or invoke node.execute() outside a loop"
        ) from exc
    nest_asyncio.apply()
    return asyncio.run(coro)


__all__ = [
    "LcaStopPolicyProvider",
    "register_fixture_policy",
    "unregister_fixture_policy",
]
