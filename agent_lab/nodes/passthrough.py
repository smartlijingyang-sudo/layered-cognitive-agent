"""Passthrough nodes — copy / constant / select / redact / dedup.

Each one is < 30 LOC, single responsibility, fully self-described via @node.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_text


@node(
    id="identity",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.PASSTHROUGH,
    description="Copy first input to first output (config may rename ports).",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.ARTIFACT)],
    provides=["passthrough_copy"],
    relates_to=["assemble_messages", "merge_messages"],
)
class Identity(Node):
    """Copy first input to first output (config may rename ports)."""

    name = "identity"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        if src not in inputs:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        return {dst: inputs[src]}


@node(
    id="constant",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.PRODUCER,
    description="Emit a constant Artifact on the first output.",
    inputs=[],
    outputs=[PortInfo("out", kind=PortKind.TEXT)],
    provides=["constant_artifact"],
)
class Constant(Node):
    """Emit a constant Artifact on the first output."""

    name = "constant"

    def execute(self, node, inputs):
        dst = node.outs[0]
        return {dst: make_text(str(node.config.get("value", "")), schema_ref=node.config.get("schema_ref", "raw"))}


@node(
    id="select",
    layer=NodeLayer.DIGEST,
    kind=NodeKind.PASSTHROUGH,
    description="Pick one input port by config.key, copy its content into one output.",
    inputs=[PortInfo("from", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.ARTIFACT)],
    provides=["port_select"],
    relates_to=["identity"],
)
class Select(Node):
    """Pick one input port by config.key, copy its content into one output."""

    name = "select"

    def execute(self, node, inputs):
        src = node.config["from"]
        dst = node.outs[0]
        return {dst: inputs.get(src, Artifact(kind=ArtifactKind.TEXT, content=""))}


@node(
    id="redact",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Drop substring patterns from text outputs. Config: patterns:[str].",
    inputs=[PortInfo("from", kind=PortKind.TEXT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.TEXT)],
    provides=["redacted_text"],
    requires=["text_input"],
    relates_to=["trust_classify", "merge_messages", "dedup"],
)
class Redact(Node):
    """Drop substring patterns from text outputs. Config: patterns:[str]."""

    name = "redact"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        patterns = node.config.get("patterns", [])
        src_a = inputs.get(src)
        if src_a is None:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        text = str(src_a.content)
        for p in patterns:
            text = text.replace(p, "[REDACTED]")
        return {dst: Artifact(kind=src_a.kind, content=text, schema_ref=src_a.schema_ref)}


@node(
    id="dedup",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Drop duplicate lines from a text content (config key: split_on).",
    inputs=[PortInfo("from", kind=PortKind.TEXT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.TEXT)],
    provides=["deduped_text"],
    relates_to=["redact", "rank"],
)
class Dedup(Node):
    """Drop duplicate lines from a text content (config key: split_on)."""

    name = "dedup"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        split_on = node.config.get("split_on", "\n")
        src_a = inputs.get(src)
        if src_a is None:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        seen: set[str] = set()
        lines = str(src_a.content).split(split_on)
        kept = [ln for ln in lines if not (ln in seen or seen.add(ln))]
        return {dst: Artifact(kind=src_a.kind, content=split_on.join(kept), schema_ref=src_a.schema_ref)}


@node(
    id="rank",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Keep first N lines (config: keep=int).",
    inputs=[PortInfo("from", kind=PortKind.TEXT, required=False)],
    outputs=[PortInfo("to", kind=PortKind.TEXT)],
    provides=["ranked_text"],
    relates_to=["dedup", "redact"],
)
class Rank(Node):
    """Keep first N lines (config: keep=int)."""

    name = "rank"

    def execute(self, node, inputs):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        keep = int(node.config.get("keep", 10))
        split_on = node.config.get("split_on", "\n")
        src_a = inputs.get(src)
        if src_a is None:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        lines = str(src_a.content).split(split_on)[:keep]
        return {dst: Artifact(kind=src_a.kind, content=split_on.join(lines), schema_ref=src_a.schema_ref)}
