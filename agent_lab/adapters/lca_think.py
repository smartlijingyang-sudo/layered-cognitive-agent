"""Adapter: agent_lab think.sub_spec ↔ LCA Brain.parse + DecisionGate.

LCA contracts consumed (read-only):
  - lca.contracts.models.core.execution.decision.Decision
  - lca.contracts.models.core.conversation.llm.LLMResponse
  - lca.contracts.protocols.think.cognition.DecisionGate
  - lca.contracts.models.core.state.state.AgentState

agent_lab provides (this file):
  - LcaThinkParseProvider: turns an LLMResponse artifact into a Decision
    artifact. Pure transform; no LCA state required.
  - LcaThinkGateProvider: wraps a DecisionGate and exposes an .enforce()
    method that turns a Decision artifact into a Decision artifact (the
    gate may rewrite or refuse). Signal ports (think_signal) are emitted
    so the agent_loop junction sees the think stage completed.

Both providers follow the same fixture_hub_name / factory / fallback
resolution as ``LcaPerceiveProvider`` so node.config stays JSON-
serializable for plan_hash.
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
# Shared: process-local fixture registry (parallels lca_perceive.py)
# ---------------------------------------------------------------------------
_FIXTURE_GATES: dict[str, Any] = {}
_FIXTURE_PARSERS: dict[str, Any] = {}


def register_fixture_gate(name: str, gate: Any) -> None:
    _FIXTURE_GATES[name] = gate


def unregister_fixture_gate(name: str) -> None:
    _FIXTURE_GATES.pop(name, None)


def register_fixture_parser(name: str, parser: Any) -> None:
    _FIXTURE_PARSERS[name] = parser


def unregister_fixture_parser(name: str) -> None:
    _FIXTURE_PARSERS.pop(name, None)


# ---------------------------------------------------------------------------
# Parse provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaThinkParseProvider:
    """Bridge agent_lab parse_decision node → LCA Decision.

    No LLM is invoked here — parsing happens against an LLMResponse that
    the upstream ``call_llm`` already produced. The provider is a pure
    transform from agent_lab's Artifact (LLMResponse-shaped dict) to a
    Decision artifact.
    """

    _parser: Any  # callable(LLMResponse) -> Decision | async Decision

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaThinkParseProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_parser_name")
        if name and name in _FIXTURE_PARSERS:
            return cls(_parser=_FIXTURE_PARSERS[name])
        # Default parser: heuristic — pure transform, no LCA dependency.
        return cls(_parser=_default_parser)

    def parse(self, response_artifact: Artifact | None) -> dict[str, Artifact]:
        response_obj = _response_from_artifact(response_artifact)
        decision = _call_maybe_async(self._parser, response_obj)
        return {
            "decision": Artifact(
                kind=ArtifactKind.FACT,
                content=_decision_to_dict(decision),
                schema_ref="decision.v1",
            )
        }


# ---------------------------------------------------------------------------
# Gate provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LcaThinkGateProvider:
    """Bridge agent_lab gate_enforce node → LCA DecisionGate.

    Resolution order for the gate:
      1. ``provider_config.fixture_gate_name`` (looks up ``_FIXTURE_GATES``)
      2. ``provider_config.gate_factory`` (module:Class form)
      3. Fallback: identity pass-through (always accepts)
    """

    _gate: Any

    @classmethod
    def from_node_config(cls, config: dict[str, Any]) -> LcaThinkGateProvider:
        cfg = config.get("provider_config") or {}
        name = cfg.get("fixture_gate_name")
        if name and name in _FIXTURE_GATES:
            return cls(_gate=_FIXTURE_GATES[name])
        factory = cfg.get("gate_factory")
        if isinstance(factory, dict) and factory.get("ref"):
            gate_cls = _import_dotted(factory["ref"])
            kwargs = dict(factory.get("kwargs") or {})
            return cls(_gate=gate_cls(**kwargs))
        # Fallback: identity gate that always passes through.
        return cls(_gate=_IdentityGate())

    def enforce(
        self,
        *,
        decision_artifact: Artifact | None,
        perception_artifact: Artifact | None = None,
        out_port: str = "enforced_decision",
    ) -> dict[str, Artifact]:
        decision_dict = decision_artifact.content if decision_artifact else {}
        if not isinstance(decision_dict, dict):
            decision_dict = {}
        decision = _decision_from_dict(decision_dict)
        # DecisionGate.enforce is async; bridge from sync node.execute().
        enforced = _run_async(self._gate.enforce(state=None, decision=decision))
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content=_decision_to_dict(enforced),
                schema_ref="decision.v1",
            ),
            "think_signal": Artifact(
                kind=ArtifactKind.FACT,
                content={
                    "decision_id": getattr(enforced, "decision_id", None),
                    "action_type": getattr(enforced, "action_type", None),
                    "ts": datetime.now(UTC).isoformat(),
                },
                schema_ref="think.signal.v1",
            ),
        }


# ---------------------------------------------------------------------------
# Defaults: pure-transform parser + identity gate
# ---------------------------------------------------------------------------


def _default_parser(response: Any) -> Any:
    """Heuristic parse — turn an LLMResponse into a Decision without LCA.

    LCA's full Brain uses ``ModularBrain`` to assemble decisions; in
    agent_lab we don't need the full chain — just enough to hand the
    Decision to ``gate_enforce`` and onward to ``act``.
    """
    from lca.contracts.models.core.execution.decision import Decision, ToolCall

    text = getattr(response, "text", "") or ""
    tool_calls_field = getattr(response, "tool_calls", None) or []
    tool_calls: list[ToolCall] = []
    for tc in tool_calls_field:
        try:
            tool_calls.append(
                ToolCall(
                    call_id=getattr(tc, "call_id", "") or "",
                    tool_name=getattr(tc, "name", "") or "",
                    arguments=dict(getattr(tc, "arguments", {}) or {}),
                )
            )
        except Exception as exc:
            # Skip malformed tool calls; agent_lab's parser is heuristic.
            import logging

            logging.getLogger(__name__).debug("skip malformed tool_call during parse: %s", exc)
            continue
    if tool_calls:
        action_type = "call_tool"
    elif text.strip():
        action_type = "respond"
    else:
        action_type = "refuse"
    return Decision(
        decision_id=f"dec_{uuid.uuid4().hex[:12]}",
        action_type=action_type,
        rationale=text[:1024],
        confidence=1.0,
        tool_calls=tool_calls,
        response_text=text or None,
    )


class _IdentityGate:
    """Pass-through gate used when no fixture / factory is configured."""

    async def enforce(self, state: Any, decision: Any) -> Any:
        return decision


# ---------------------------------------------------------------------------
# Helpers — artifact ⇄ LCA dataclass conversions
# ---------------------------------------------------------------------------


def _response_from_artifact(artifact: Artifact | None) -> Any:
    """Reconstruct an LLMResponse-like object from an Artifact."""
    from lca.contracts.models.core.conversation.llm import (
        LLMResponse,
        NativeToolCall,
        TokenUsage,
    )

    if artifact is None or artifact.content is None:
        return LLMResponse(text="", tool_calls=[])
    content = artifact.content
    if isinstance(content, dict):
        text = str(content.get("text") or content.get("content") or "")
        raw_calls = content.get("tool_calls") or []
    else:
        text = str(content)
        raw_calls = []
    tool_calls: list[NativeToolCall] = []
    for tc in raw_calls:
        if isinstance(tc, dict):
            tool_calls.append(
                NativeToolCall(
                    call_id=str(tc.get("id") or tc.get("call_id") or ""),
                    name=str(tc.get("name") or ""),
                    arguments=dict(tc.get("arguments") or tc.get("args") or {}),
                )
            )
    usage_raw = content.get("usage") if isinstance(content, dict) else None
    usage = None
    if isinstance(usage_raw, dict):
        usage = TokenUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
        )
    return LLMResponse(
        text=text,
        model=str(content.get("model", "") if isinstance(content, dict) else ""),
        usage=usage,
        finish_reason=(content.get("finish_reason") if isinstance(content, dict) else None),
        tool_calls=tool_calls,
    )


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    return {
        "decision_id": getattr(decision, "decision_id", ""),
        "action_type": getattr(decision, "action_type", ""),
        "rationale": getattr(decision, "rationale", "") or "",
        "confidence": float(getattr(decision, "confidence", 1.0) or 1.0),
        "tool_calls": [
            {
                "call_id": getattr(tc, "call_id", ""),
                "name": (getattr(tc, "tool_name", None) or getattr(tc, "name", "") or ""),
                "arguments": dict(getattr(tc, "arguments", {}) or {}),
            }
            for tc in (getattr(decision, "tool_calls", []) or [])
        ],
        "delegations": [
            getattr(d, "__dict__", d) for d in (getattr(decision, "delegations", []) or [])
        ],
        "response_text": getattr(decision, "response_text", None),
        "degraded_from": getattr(decision, "degraded_from", None),
        "extra": dict(getattr(decision, "extra", {}) or {}),
    }


def _decision_from_dict(d: dict[str, Any]) -> Any:
    from lca.contracts.models.core.execution.decision import Decision, ToolCall

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
        confidence=float(d.get("confidence") or 1.0),
        tool_calls=tool_calls,
        response_text=d.get("response_text"),
        degraded_from=d.get("degraded_from"),
        extra=dict(d.get("extra") or {}),
    )


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
            "LcaThink* provider called inside a running event loop; "
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
    "LcaThinkGateProvider",
    "LcaThinkParseProvider",
    "register_fixture_gate",
    "register_fixture_parser",
    "unregister_fixture_gate",
    "unregister_fixture_parser",
]
