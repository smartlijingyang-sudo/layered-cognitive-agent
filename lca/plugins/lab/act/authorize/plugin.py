"""act.authorize — Intent + allow → stamped Intent(verdict).

worker: authorize(*, intent, allow) -> Intent
kind: TRANSFORMER
out_port: authorized
in: intent=intent
config: allow
"""
from dataclasses import dataclass, replace
from typing import Any

from agent_lab.primitives.artifact import Artifact


VERDICT_ALLOW = "allow"
VERDICT_DENY = "deny"
VERDICT_SKIP = "skip"

EFFECT_KIND_NO_TOOL_VERDICT = frozenset(
    {"respond", "stop", "ask_human", "delegate", "handoff"}
)
EFFECT_KIND_REQUIRES_TOOL = frozenset({"use_tool", "call_tool"})


@dataclass(frozen=True, slots=True)
class Intent:
    action_type: str
    tool: str | None
    args: dict[str, Any]
    effect_kind: str
    verdict: str = "allow"


def authorize(*, intent: Artifact | None, allow: list[str] | tuple[str, ...] | frozenset[str] | None = None) -> Intent:
    """从 Intent artifact content 派生 stamped Intent。"""
    content: dict[str, Any] = (
        dict(intent.content) if intent is not None and isinstance(intent.content, dict) else {}
    )
    parsed = Intent(
        action_type=content.get("action_type", ""),
        tool=content.get("tool"),
        args=dict(content.get("args") or {}),
        effect_kind=content.get("effect_kind", "use_tool"),
        verdict=content.get("verdict", VERDICT_ALLOW),
    )
    allow_set = frozenset(allow or ())
    if parsed.effect_kind == "no_effect":
        return replace(parsed, verdict=VERDICT_SKIP)
    if parsed.effect_kind in EFFECT_KIND_NO_TOOL_VERDICT:
        return replace(parsed, verdict=VERDICT_ALLOW)
    if parsed.effect_kind in EFFECT_KIND_REQUIRES_TOOL:
        verdict = VERDICT_ALLOW if parsed.tool in allow_set else VERDICT_DENY
        return replace(parsed, verdict=verdict)
    return replace(parsed, verdict=VERDICT_SKIP)


__all__ = [
    "EFFECT_KIND_NO_TOOL_VERDICT",
    "EFFECT_KIND_REQUIRES_TOOL",
    "Intent",
    "VERDICT_ALLOW",
    "VERDICT_DENY",
    "VERDICT_SKIP",
    "authorize",
]
