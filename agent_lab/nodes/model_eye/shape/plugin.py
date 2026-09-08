"""model_eye.shape — fold safe_sight into an ordered OpenAI message list.

Fixed order (deterministic):
  1. system (if present) as role=system
  2. session/history messages
  3. perceive_items (as messages; role defaults to user when missing)
  4. observation (as role=tool text, or passthrough dict)
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="model_eye.shape",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.ASSEMBLER,
    description="Shape safe_sight into an ordered OpenAI-style messages list.",
    inputs=[PortInfo("safe_sight", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
    provides=["model_eye_messages"],
    requires=["model_eye_safe_sight"],
    relates_to=["model_eye.guard", "model_eye.freeze"],
)
class ModelEyeShape(Node):
    name = "model_eye.shape"

    def execute(self, node, inputs):
        src = node.config.get("from", "safe_sight")
        out = node.config.get("to", "messages")
        sight_a = inputs.get(src)
        sight: dict[str, Any] = dict(sight_a.content) if (
            sight_a is not None and isinstance(sight_a.content, dict)
        ) else {}

        messages: list[dict[str, Any]] = []
        system = sight.get("system")
        if isinstance(system, str) and system:
            messages.append({"role": "system", "content": system})

        for m in sight.get("messages") or []:
            if isinstance(m, dict):
                messages.append(dict(m))

        for it in sight.get("perceive_items") or []:
            if not isinstance(it, dict):
                continue
            if "role" in it and "content" in it:
                messages.append({k: v for k, v in it.items() if k != "provenance"})
            else:
                content = it.get("content", it.get("text", str(it)))
                messages.append({"role": it.get("role", "user"), "content": content})

        obs = sight.get("observation")
        if isinstance(obs, str) and obs:
            messages.append({"role": "tool", "content": obs})
        elif isinstance(obs, dict):
            if "role" in obs and "content" in obs:
                messages.append(dict(obs))
            else:
                messages.append({"role": "tool", "content": str(obs)})
        elif isinstance(obs, list):
            for item in obs:
                if isinstance(item, dict):
                    messages.append(dict(item))
                elif isinstance(item, str) and item:
                    messages.append({"role": "tool", "content": item})

        return {
            out: Artifact(
                kind=ArtifactKind.MESSAGE,
                content=messages,
                schema_ref="openai.messages.v1",
            )
        }
