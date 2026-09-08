"""model_eye.freeze — validate + digest + emit frozen ContextManifest.

Single write authority for ContextManifest in agent_lab. Fail-loud when
required roles are missing (no half-committed manifest).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="model_eye.freeze",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.PRODUCER,
    description=(
        "Freeze messages into ContextManifest (digest + schema). "
        "Raises if required_roles are missing."
    ),
    inputs=[PortInfo("messages", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("manifest", kind=PortKind.MANIFEST)],
    provides=["context_manifest"],
    requires=["model_eye_messages"],
    emits=["context_manifest"],
    relates_to=["model_eye.shape"],
)
class ModelEyeFreeze(Node):
    name = "model_eye.freeze"

    def execute(self, node, inputs):
        src = node.config.get("from", "messages")
        out = node.config.get("to", "manifest")
        required_roles = list(node.config.get("required_roles", ["user"]))
        src_a = inputs.get(src)
        messages: list[dict[str, Any]] = []
        if src_a is not None and isinstance(src_a.content, list):
            messages = [dict(m) for m in src_a.content if isinstance(m, dict)]

        roles = {m.get("role") for m in messages}
        missing = [r for r in required_roles if r not in roles]
        if missing:
            raise ValueError(
                f"model_eye.freeze: required roles missing: {missing}; "
                f"have roles={sorted(r for r in roles if r is not None)}"
            )

        digest = _digest(messages)
        manifest = {
            "messages": messages,
            "digest": digest,
            "schema_version": "context.manifest.v1",
            "committed": True,
        }
        return {
            out: Artifact(
                kind=ArtifactKind.MANIFEST,
                content=manifest,
                schema_ref="context.manifest.v1",
            )
        }


def _digest(messages: list[dict[str, Any]]) -> str:
    payload = json.dumps(messages, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
