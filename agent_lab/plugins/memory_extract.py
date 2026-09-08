"""MemoryExtractPlugin — on_reflection hook that stashes memory candidates.

Canonical candidate derivation for the reflect phase lives in
``reflect.extract`` (pure transform). This plugin remains for
agent_loop hook fan-out when a Reflection artifact crosses the
on_reflection event: it mirrors the same lesson / correction / extra
branches into ``payload["memory_candidates"]``.

Behaviour:
  - if lesson is truthy  → candidate {"kind": "lesson", ...}
  - if correction is dict → candidate {"kind": "correction", ...}
  - if extra is dict and truthy → candidate {"kind": "extra", ...}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_lab.plugins.base import GraphPlugin, HookContext, register_plugin


@register_plugin
@dataclass(frozen=True)
class MemoryExtractPlugin(GraphPlugin):
    """Derive memory candidates from a Reflection artifact."""

    name: str = "default_memory_extract"
    kind: str = "memory_extract"
    binds: tuple = ()
    config: dict[str, Any] = field(default_factory=dict)

    def on_reflection(self, ctx: HookContext) -> HookContext:
        artifact = ctx.payload.get("artifact")
        if artifact is None:
            return ctx
        content = getattr(artifact, "content", None)
        if not isinstance(content, dict):
            return ctx

        candidates: list[dict] = []
        lesson = content.get("lesson")
        if lesson:
            candidates.append(
                {
                    "kind": "lesson",
                    "verdict": content.get("verdict", ""),
                    "text": lesson,
                    "reflection_id": content.get("reflection_id", ""),
                }
            )
        correction = content.get("correction")
        if isinstance(correction, dict) and correction:
            candidates.append(
                {
                    "kind": "correction",
                    "decision_id": correction.get("decision_id", ""),
                    "action_type": correction.get("action_type", ""),
                    "reflection_id": content.get("reflection_id", ""),
                }
            )
        extra = content.get("extra")
        if isinstance(extra, dict) and extra:
            candidates.append(
                {
                    "kind": "extra",
                    "payload": extra,
                    "reflection_id": content.get("reflection_id", ""),
                }
            )

        # Stash the candidates in ctx.payload so the runner (or the node)
        # can pick them up and emit a separate artifact. The reflection
        # artifact itself is left untouched.
        return ctx.with_value(payload={**ctx.payload, "memory_candidates": {"items": candidates}})


__all__ = ["MemoryExtractPlugin"]
