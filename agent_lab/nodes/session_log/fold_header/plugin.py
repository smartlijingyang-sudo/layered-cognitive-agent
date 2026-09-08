"""session_log/fold_header — fold the Session header (system/tools/config).

Distinct from snapshot_events (events list) and derive_messages (folded
messages). The header is the **header fold** — system prompt + tool
schemas + config — that the model-visible assembler pulls together for
the LLM.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.fold.header",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.TRANSFORMER,
    description="Fold the Session header (system/tools/config) for the LLM assembler.",
    inputs=[],
    outputs=[PortInfo("header", kind=PortKind.FACT)],
    provides=["session_header"],
)
class FoldHeader(Node):
    name = "session_log.fold.header"

    def execute(self, node, inputs):
        from agent_lab._session_holder import session
        sess = session()
        header = sess.request_header()
        return {"header": Artifact(
            kind=ArtifactKind.FACT,
            content=_header_to_dict(header),
            schema_ref="session.header.v1",
        )}


def _header_to_dict(header):
    if header is None:
        return {}
    if isinstance(header, dict):
        return dict(header)
    # dataclass-like
    out = {}
    for k in ("system", "tools", "config", "schema_version"):
        v = getattr(header, k, None)
        if v is not None:
            out[k] = v
    return out
