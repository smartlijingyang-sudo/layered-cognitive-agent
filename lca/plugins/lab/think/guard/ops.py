from __future__ import annotations

"""Inlined ops (PR-D) — source: feat worktree."""

import asyncio
import importlib
import uuid
from datetime import UTC, datetime
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind

_FIXTURE_GATES: dict[str, Any] = {}


def register_fixture_gate(name: str, gate: Any) -> None:
    _FIXTURE_GATES[name] = gate


def unregister_fixture_gate(name: str) -> None:
    _FIXTURE_GATES.pop(name, None)


def enforce_decision(
    decision_artifact: Artifact | None,
    state_artifact: Artifact | None,
    *,
    config: dict[str, Any],
    out_port: str = "enforced_decision",
) -> dict[str, Artifact]:
    gate, gate_label = resolve_gate(config)
    decision = _decision_from_artifact(decision_artifact)
    state = _state_from_artifact(state_artifact)
    enforced = _run_async(gate.enforce(state=state, decision=decision))
    enforced_dict = _decision_to_dict(enforced)
    return {
        out_port: Artifact(
            kind=ArtifactKind.FACT,
            content=enforced_dict,
            schema_ref="decision.v1",
        ),
        "think_signal": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "decision_id": enforced_dict.get("decision_id"),
                "action_type": enforced_dict.get("action_type"),
                "gate": gate_label,
                "ts": datetime.now(UTC).isoformat(),
            },
            schema_ref="think.signal.v1",
        ),
    }


def resolve_gate(cfg: dict[str, Any]) -> tuple[Any, str]:
    live = cfg.get("gate")
    if live is not None and hasattr(live, "enforce"):
        return live, type(live).__name__

    name = cfg.get("fixture_gate_name")
    if name:
        if name not in _FIXTURE_GATES:
            raise ValueError(f"think.guard: unknown fixture_gate_name={name!r}")
        return _FIXTURE_GATES[name], f"fixture:{name}"

    if cfg.get("null_gate") is True:
        return _NullGate(), "null"

    factory = cfg.get("gate_factory")
    if isinstance(factory, dict) and factory.get("ref"):
        return _build_factory_gate(factory, allow_empty=bool(cfg.get("allow_empty_chain")))

    raise ValueError(
        "think.guard: no gate configured — set null_gate: true, "
        "fixture_gate_name, gate_factory, or gate"
    )


def _build_factory_gate(factory: dict[str, Any], *, allow_empty: bool) -> tuple[Any, str]:
    gate_cls = _import_dotted(factory["ref"])
    kwargs = dict(factory.get("kwargs") or {})
    members_raw = factory.get("members") or factory.get("gates") or []
    members: list[Any] = []
    for m in members_raw:
        if hasattr(m, "enforce"):
            members.append(m)
            continue
        if isinstance(m, dict) and m.get("ref"):
            m_cls = _import_dotted(m["ref"])
            members.append(m_cls(**dict(m.get("kwargs") or {})))
            continue
        raise ValueError(f"think.guard: invalid gate member {m!r}")

    gate = gate_cls(*members, **kwargs) if members else gate_cls(**kwargs)
    empty = True
    if hasattr(gate, "_gates"):
        empty = len(gate._gates) == 0
    elif members:
        empty = False
    if empty and not allow_empty:
        raise ValueError(
            "think.guard: empty DecisionGate chain; "
            "pass members, set allow_empty_chain: true, or use null_gate: true"
        )
    return gate, getattr(gate_cls, "__name__", "factory")


class _NullGate:
    async def enforce(self, state: Any, decision: Any) -> Any:
        return decision


def _decision_from_artifact(artifact: Artifact | None) -> Any:
    from lca.contracts.models.core.execution.decision import Decision, ToolCall

    d: dict[str, Any] = {}
    if artifact is not None and isinstance(artifact.content, dict):
        d = artifact.content
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
        decision_id=str(d.get("decision_id") or f"dec_{uuid.uuid4().hex[:12]}"),
        action_type=str(d.get("action_type") or "respond"),
        rationale=str(d.get("rationale") or ""),
        confidence=float(d["confidence"])
        if "confidence" in d and d["confidence"] is not None
        else 1.0,
        tool_calls=tool_calls,
        response_text=d.get("response_text"),
        degraded_from=d.get("degraded_from"),
        extra=dict(d.get("extra") or {}),
    )


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    conf = getattr(decision, "confidence", None)
    delegations = []
    for d in getattr(decision, "delegations", []) or []:
        if hasattr(d, "subtask"):
            delegations.append(
                {
                    "subtask": d.subtask,
                    "target_role": d.target_role,
                    "target_agent_id": d.target_agent_id,
                }
            )
            continue
        if isinstance(d, dict):
            delegations.append(dict(d))
            continue
        delegations.append(getattr(d, "__dict__", d))
    return {
        "decision_id": getattr(decision, "decision_id", ""),
        "action_type": getattr(decision, "action_type", ""),
        "rationale": getattr(decision, "rationale", "") or "",
        "confidence": float(1.0 if conf is None else conf),
        "tool_calls": [
            {
                "call_id": getattr(tc, "call_id", ""),
                "name": (getattr(tc, "tool_name", None) or getattr(tc, "name", "") or ""),
                "arguments": dict(getattr(tc, "arguments", {}) or {}),
            }
            for tc in (getattr(decision, "tool_calls", []) or [])
        ],
        "delegations": delegations,
        "response_text": getattr(decision, "response_text", None),
        "degraded_from": getattr(decision, "degraded_from", None),
        "extra": dict(getattr(decision, "extra", {}) or {}),
    }


def _state_from_artifact(artifact: Artifact | None) -> Any:
    if artifact is None or not isinstance(artifact.content, dict):
        return None
    content = artifact.content
    from lca.contracts.models.core.state.state import AgentState

    return AgentState(
        trace_id=str(content.get("trace_id") or ""),
        task=str(content.get("task") or ""),
        budget=content.get("budget"),
        step=int(content.get("step") or 0),
    )


def _import_dotted(ref: str) -> Any:
    if ":" in ref:
        mod, _, attr = ref.partition(":")
        return getattr(importlib.import_module(mod), attr)
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
            "think.guard called inside a running event loop; "
            "install nest_asyncio or invoke node.execute() outside a loop"
        ) from exc
    nest_asyncio.apply()
    return asyncio.run(coro)
