"""perceive.aggregate — fold sensors into a perceive.bundle for model_eye.

Pure composition: three sensor artifacts (user_turn, tool_results,
retrieved_context) → one ``perceive.bundle`` (items + digest). NO hub,
NO Protocol, NO state mutation. ContextManifest is produced only by
``model_eye.freeze`` (perceive mounts model_eye as a sub_spec).

Inputs come from the three independent sense chains:
  - user_turn       : OpenAI-style message (latest user turn)
  - tool_results    : list[dict] of {role: "tool", ...} messages
  - retrieved_context : list[dict] ContextItem-shaped memory items
"""
from __future__ import annotations

import hashlib
import json

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="perceive.aggregate",
    layer=NodeLayer.PHASE,
    kind=NodeKind.ASSEMBLER,
    description="Aggregate user_turn + tool_results + retrieved_context into perceive.bundle for model_eye.",
    inputs=[
        PortInfo("user_turn", kind=PortKind.MESSAGE, required=False),
        PortInfo("tool_results", kind=PortKind.MESSAGE, required=False),
        PortInfo("retrieved_context", kind=PortKind.ARTIFACT, required=False),
    ],
    outputs=[PortInfo("bundle", kind=PortKind.FACT)],
    provides=["perceive_bundle"],
    emits=[],
)
class PerceiveAggregate(Node):
    name = "perceive.aggregate"

    def execute(self, node, inputs):
        items = _collect(inputs)
        digest = _digest(items)
        bundle = Artifact(
            kind=ArtifactKind.FACT,
            content={
                "items": items,
                "digest": digest,
                "schema_version": "perceive.bundle.v1",
                "extra": {},
            },
            schema_ref="perceive.bundle.v1",
        )
        out_port = node.config.get("to", node.outs[0] if node.outs else "bundle")
        return {out_port: bundle}


def _collect(inputs: dict) -> list[dict]:
    """Pull ContextItems from the three sensor artifacts. Each sensor emits
    either a dict (single ContextItem) or a list of dicts. We wrap dicts
    in lists and concat in a fixed order so the manifest is deterministic."""
    items: list[dict] = []

    # user_turn: a single message dict; wrap in list and tag provenance.
    ut_a = inputs.get("user_turn")
    if ut_a is not None:
        msg = ut_a.content if hasattr(ut_a, "content") else None
        if isinstance(msg, dict):
            items.append({**msg, "provenance": "sense.user"})
        elif isinstance(msg, list):
            items.extend({**m, "provenance": "sense.user"} for m in msg if isinstance(m, dict))

    # tool_results: a list of {role: "tool", ...} message dicts.
    tr_a = inputs.get("tool_results")
    if tr_a is not None:
        msgs = tr_a.content if hasattr(tr_a, "content") else None
        if isinstance(msgs, list):
            items.extend({**m, "provenance": "sense.tool_results"} for m in msgs if isinstance(m, dict))
        elif isinstance(msgs, dict):
            items.append({**msgs, "provenance": "sense.tool_results"})

    # retrieved_context: already-normalized list of ContextItem-shaped dicts.
    rc_a = inputs.get("retrieved_context")
    if rc_a is not None:
        ctx = rc_a.content if hasattr(rc_a, "content") else None
        if isinstance(ctx, list):
            items.extend(it for it in ctx if isinstance(it, dict))

    return items


def _digest(items: list[dict]) -> str:
    """Content-addressable digest: sha256 over canonical JSON of items.

    sort_keys + ensure_ascii + separators=(",", ":") makes the encoding
    stable across Python versions and dict-insertion order.
    """
    payload = json.dumps(items, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
