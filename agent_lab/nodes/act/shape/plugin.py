"""act.shape — Decision → Intent for Body.act.

Normalizes Think labels onto the LCA ActionType closed set
(``call_tool`` → ``use_tool``; ``refuse`` → ``respond``). Every
recognized action becomes an Intent that authorize/execute can hand to
``SimpleBody.act``. Does not authorize or execute.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_TOOL_ACTION_ALIASES = frozenset({"call_tool", "use_tool"})
# Body-handled non-tool actions (solo + terminal + team).
_BODY_ACTIONS = frozenset({"respond", "stop", "ask_human", "delegate", "handoff"})
_TEAM_ACTIONS = frozenset({"delegate", "handoff"})


@node(
    id="act.shape",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.PRODUCER,
    description=(
        "Decision → Intent. Canonicalizes action_type for SimpleBody.act "
        "(use_tool / respond / stop / ask_human)."
    ),
    inputs=[PortInfo("decision", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("intent", kind=PortKind.INTENT)],
    provides=["tool_intent"],
    consumes=["decision"],
    emits=["tool_intent"],
    relates_to=["act.authorize", "act.execute"],
)
class ActShape(Node):
    """Package Decision into an Intent Body can execute."""

    name = "act.shape"

    def execute(self, node, inputs):
        out_port = node.config.get("to", "intent")
        decision_a = inputs.get(node.config.get("from", "decision"))
        raw = _content(decision_a)

        # Legacy raw args ({tool, args}) still accepted for demos / tests.
        if "action_type" not in raw and isinstance(raw.get("tool"), str):
            return {
                out_port: Artifact(
                    kind=ArtifactKind.INTENT,
                    content=_tool_intent(
                        decision_id=str(raw.get("decision_id") or ""),
                        tool_calls=[
                            {
                                "call_id": "",
                                "name": raw["tool"],
                                "arguments": raw.get("args", {}) or {},
                            }
                        ],
                        rationale=str(raw.get("rationale") or ""),
                        confidence=float(raw.get("confidence") or 1.0),
                    ),
                    schema_ref="tool.intent.v1",
                )
            }

        action_type = str(raw.get("action_type") or "")
        decision_id = str(raw.get("decision_id") or "")
        rationale = str(raw.get("rationale") or "")
        confidence = float(raw.get("confidence") or 1.0)

        if action_type in _TOOL_ACTION_ALIASES:
            tool_calls = _normalize_tool_calls(raw.get("tool_calls") or [])
            if not tool_calls:
                return {
                    out_port: Artifact(
                        kind=ArtifactKind.INTENT,
                        content={
                            "effect_kind": "no_effect",
                            "tool": "__none__",
                            "args": {},
                            "tool_calls": [],
                            "decision_id": decision_id,
                            "action_type": "use_tool",
                            "reason": "use_tool without tool_calls",
                        },
                        schema_ref="tool.intent.v1",
                    )
                }
            return {
                out_port: Artifact(
                    kind=ArtifactKind.INTENT,
                    content=_tool_intent(
                        decision_id=decision_id,
                        tool_calls=tool_calls,
                        rationale=rationale,
                        confidence=confidence,
                    ),
                    schema_ref="tool.intent.v1",
                )
            }

        # refuse is agent_lab-only; Body has no refuse — map to respond.
        if action_type == "refuse":
            text = raw.get("response_text") or rationale or ""
            return {
                out_port: Artifact(
                    kind=ArtifactKind.INTENT,
                    content={
                        "effect_kind": "respond",
                        "tool": "__none__",
                        "args": {},
                        "tool_calls": [],
                        "decision_id": decision_id,
                        "action_type": "respond",
                        "response_text": text,
                        "rationale": rationale,
                        "confidence": confidence,
                        "degraded_from": "refuse",
                    },
                    schema_ref="tool.intent.v1",
                )
            }

        if action_type in _BODY_ACTIONS:
            content = {
                "effect_kind": action_type,
                "tool": "__none__",
                "args": {},
                "tool_calls": [],
                "decision_id": decision_id,
                "action_type": action_type,
                "response_text": raw.get("response_text"),
                "rationale": rationale,
                "confidence": confidence,
            }
            if action_type in _TEAM_ACTIONS:
                content["delegations"] = _normalize_delegations(raw.get("delegations") or [])
            return {
                out_port: Artifact(
                    kind=ArtifactKind.INTENT,
                    content=content,
                    schema_ref="tool.intent.v1",
                )
            }

        # Unknown action_type — skip Body rather than invent authority.
        return {
            out_port: Artifact(
                kind=ArtifactKind.INTENT,
                content={
                    "effect_kind": "no_effect",
                    "tool": "__none__",
                    "args": {},
                    "tool_calls": [],
                    "decision_id": decision_id,
                    "action_type": action_type or "respond",
                    "response_text": raw.get("response_text"),
                    "reason": f"unregistered action_type: {action_type!r}",
                },
                schema_ref="tool.intent.v1",
            )
        }


def _tool_intent(
    *,
    decision_id: str,
    tool_calls: list[dict[str, Any]],
    rationale: str,
    confidence: float,
) -> dict[str, Any]:
    first = tool_calls[0]
    return {
        "effect_kind": "use_tool",
        "tool": first["name"],
        "args": first["arguments"],
        "call_id": first["call_id"],
        "tool_calls": tool_calls,
        "decision_id": decision_id,
        "action_type": "use_tool",
        "rationale": rationale,
        "confidence": confidence,
    }


def _normalize_tool_calls(raw_calls: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in raw_calls:
        if not isinstance(tc, dict):
            continue
        name = str(tc.get("name") or tc.get("tool_name") or "")
        if not name:
            continue
        args = tc.get("arguments") or tc.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        out.append(
            {
                "call_id": str(tc.get("call_id") or ""),
                "name": name,
                "arguments": args,
            }
        )
    return out


def _normalize_delegations(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        subtask = str(item.get("subtask") or "")
        if not subtask:
            continue
        out.append(
            {
                "subtask": subtask,
                "target_role": item.get("target_role") or "lab_echo",
                "target_agent_id": item.get("target_agent_id"),
                "protocol": item.get("protocol") or "internal",
                "timeout_s": item.get("timeout_s"),
            }
        )
    return out


def _content(artifact: Any) -> dict[str, Any]:
    if artifact is None:
        return {}
    raw = getattr(artifact, "content", None)
    return raw if isinstance(raw, dict) else {}
