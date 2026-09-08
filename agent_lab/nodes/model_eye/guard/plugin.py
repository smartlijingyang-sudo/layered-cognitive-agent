"""model_eye.guard — keep untrusted / noisy / secret bytes out of the eye.

Applies trust tagging, optional dedup, top-K truncate, and redact patterns
to the ``sight`` bag. Graph-level ADR-0206 trust→dedup→rank→redact chain
collapsed into one node (config-driven; defaults are permissive).
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="model_eye.guard",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.VALIDATOR,
    description=(
        "Guard sight: trust labels + optional dedup/keep/redact. "
        "Config: trustable_kinds, keep, patterns, split_on."
    ),
    inputs=[PortInfo("sight", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("safe_sight", kind=PortKind.FACT)],
    provides=["model_eye_safe_sight"],
    requires=["model_eye_sight"],
    relates_to=["model_eye.see", "model_eye.shape"],
)
class ModelEyeGuard(Node):
    name = "model_eye.guard"

    def execute(self, node, inputs):
        src = node.config.get("from", "sight")
        out = node.config.get("to", "safe_sight")
        sight_a = inputs.get(src)
        sight: dict[str, Any] = dict(sight_a.content) if (
            sight_a is not None and isinstance(sight_a.content, dict)
        ) else {}

        trustable = set(node.config.get("trustable_kinds", ["text", "message", "manifest", "fact"]))
        keep = int(node.config.get("keep", 200))
        patterns = list(node.config.get("patterns", []) or [])
        split_on = node.config.get("split_on", "\n")

        messages = list(sight.get("messages") or [])
        perceive_items = list(sight.get("perceive_items") or [])
        observation = sight.get("observation")

        messages = _dedup_messages(messages)
        perceive_items = _dedup_dicts(perceive_items)
        if keep > 0:
            messages = messages[:keep]
            perceive_items = perceive_items[:keep]

        if patterns:
            messages = [_redact_obj(m, patterns) for m in messages]
            perceive_items = [_redact_obj(it, patterns) for it in perceive_items]
            if isinstance(observation, str):
                observation = _redact_text(observation, patterns)
            elif isinstance(observation, dict):
                observation = _redact_obj(observation, patterns)

        labels = [
            {"port": "messages", "trust": "trusted" if "message" in trustable else "untrusted"},
            {"port": "perceive_items", "trust": "trusted" if "fact" in trustable else "untrusted"},
            {"port": "observation", "trust": "trusted" if "text" in trustable else "untrusted"},
        ]

        safe = {
            "messages": messages,
            "system": sight.get("system"),
            "config": sight.get("config"),
            "tools": list(sight.get("tools") or []),
            "perceive_items": perceive_items,
            "observation": observation,
            "trust_labels": labels,
            "split_on": split_on,
        }
        return {
            out: Artifact(
                kind=ArtifactKind.FACT,
                content=safe,
                schema_ref="model_eye.safe_sight.v1",
            )
        }


def _dedup_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        key = repr(sorted(m.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(m))
    return out


def _dedup_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = repr(sorted(it.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(it))
    return out


def _redact_text(text: str, patterns: list[str]) -> str:
    for pat in patterns:
        text = text.replace(pat, "[REDACTED]")
    return text


def _redact_obj(obj: dict[str, Any], patterns: list[str]) -> dict[str, Any]:
    out = dict(obj)
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = _redact_text(v, patterns)
    return out
