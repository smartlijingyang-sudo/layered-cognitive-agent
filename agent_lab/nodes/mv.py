"""Model-visible assembly nodes.

These are the workers in the mv.assemble sub-graph (ADR-0206 §5.3).
"""

from __future__ import annotations

from agent_lab.graph.spec import InfoNode
from agent_lab.nodes.base import Node, register
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@register
class TrustClassify(Node):
    """Tag inputs with trust level (config.trustable_kinds:[str])."""

    name = "trust_classify"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        trustable = set(node.config.get("trustable_kinds", []))
        out_port = node.outs[0]
        labeled = []
        for k, a in inputs.items():
            label = "trusted" if a.kind.value in trustable else "untrusted"
            labeled.append({"port": k, "kind": a.kind.value, "trust": label, "digest": a.short_id()})
        return {out_port: Artifact(
            kind=ArtifactKind.FACT,
            content=labeled,
            schema_ref="trust.labels.v1",
        )}


@register
class MergeMessages(Node):
    """Combine multiple message-list artifacts into one ordered list."""

    name = "merge_messages"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        out_port = node.outs[0]
        order = node.config.get("order", list(inputs.keys()))
        merged: list = []
        for k in order:
            a = inputs.get(k)
            if a is None:
                continue
            content = a.content
            if isinstance(content, list):
                merged.extend(content)
            elif isinstance(content, str):
                merged.append({"role": k, "content": content})
            else:
                merged.append({"role": k, "content": str(content)})
        return {out_port: Artifact(
            kind=ArtifactKind.MESSAGE,
            content=merged,
            schema_ref="openai.messages.v1",
        )}


@register
class ValidateManifest(Node):
    """Sanity-check that messages are non-empty and contain required roles."""

    name = "validate_manifest"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        out_port = node.outs[0]
        src = node.config.get("from", node.ins[0])
        required_roles = node.config.get("required_roles", [])
        src_a = inputs.get(src)
        messages = src_a.content if src_a else []
        roles = {m.get("role") for m in messages if isinstance(m, dict)}
        ok = all(r in roles for r in required_roles)
        return {out_port: Artifact(
            kind=ArtifactKind.FACT,
            content={"valid": ok, "missing": [r for r in required_roles if r not in roles]},
            schema_ref="manifest.validate.v1",
        )}
