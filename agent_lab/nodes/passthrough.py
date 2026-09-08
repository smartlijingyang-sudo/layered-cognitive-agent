"""Passthrough nodes — copy / constant / select / redact / dedup.

Each one is < 30 LOC, single responsibility.
"""

from __future__ import annotations

from agent_lab.graph.spec import InfoNode
from agent_lab.nodes.base import Node, register
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_text


@register
class Identity(Node):
    """Copy first input to first output (config may rename ports)."""

    name = "identity"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        if src not in inputs:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        return {dst: inputs[src]}


@register
class Constant(Node):
    """Emit a constant Artifact on the first output."""

    name = "constant"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        dst = node.outs[0]
        return {dst: make_text(str(node.config.get("value", "")), schema_ref=node.config.get("schema_ref", "raw"))}


@register
class Select(Node):
    """Pick one input port by config.key, copy its content into one output."""

    name = "select"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        src = node.config["from"]
        dst = node.outs[0]
        return {dst: inputs.get(src, Artifact(kind=ArtifactKind.TEXT, content=""))}


@register
class Redact(Node):
    """Drop substring patterns from text outputs. Config: patterns:[str]."""

    name = "redact"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
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


@register
class Dedup(Node):
    """Drop duplicate lines from a text content (config key: split_on)."""

    name = "dedup"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
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


@register
class Rank(Node):
    """Keep first N lines (config: keep=int)."""

    name = "rank"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        keep = int(node.config.get("keep", 10))
        split_on = node.config.get("split_on", "\n")
        src_a = inputs.get(src)
        if src_a is None:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        lines = str(src_a.content).split(split_on)[:keep]
        return {dst: Artifact(kind=src_a.kind, content=split_on.join(lines), schema_ref=src_a.schema_ref)}
