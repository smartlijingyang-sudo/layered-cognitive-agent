"""act.shape — Decision → Intent.

worker: shape(*, decision) -> Intent
kind: TRANSFORMER
out_port: intent
"""
from dataclasses import dataclass
from typing import Any

from agent_lab.primitives.artifact import Artifact


EFFECT_KIND_DEFAULT = "use_tool"


@dataclass(frozen=True, slots=True)
class Intent:
    action_type: str
    tool: str | None
    args: dict[str, Any]
    effect_kind: str
    verdict: str = "allow"


def shape(*, decision: Artifact | None) -> Intent:
    """从 Decision artifact 的 content 派生 Intent。

    graph 层传的是 Artifact;worker 只读 ``.content`` 字典拿 typed 字段。
    """
    content: dict[str, Any] = (
        dict(decision.content) if decision is not None and isinstance(decision.content, dict) else {}
    )
    tool_calls = content.get("tool_calls") or []
    first_call = tool_calls[0] if tool_calls else None
    if isinstance(first_call, dict):
        tool = first_call.get("tool_name")
        args = dict(first_call.get("arguments") or {})
    else:
        tool = content.get("tool")
        args = dict(content.get("args") or {})
    return Intent(
        action_type=content.get("action_type", ""),
        tool=tool,
        args=args,
        effect_kind=content.get("effect_kind", EFFECT_KIND_DEFAULT),
    )


__all__ = ["EFFECT_KIND_DEFAULT", "Intent", "shape"]
