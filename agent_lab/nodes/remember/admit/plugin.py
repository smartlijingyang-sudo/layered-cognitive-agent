"""remember.admit — filter memory_candidates into admitted items.

Uses the remember_admit policy (control slot / fixture). Does not write
Session or MemorySystem; only gates what commit may persist.
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


def _items_from_candidates(artifact: Artifact | None) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    content = getattr(artifact, "content", None)
    if not isinstance(content, dict):
        return []
    items = content.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


@node(
    id="remember.admit",
    layer=NodeLayer.PHASE,
    kind=NodeKind.VALIDATOR,
    description=(
        "Filter memory_candidates via remember_admit policy; emit admitted "
        "items for commit. No durable write."
    ),
    inputs=[
        PortInfo("in_candidates", kind=PortKind.FACT, required=False),
        PortInfo("in_observation", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("admitted", kind=PortKind.FACT)],
    provides=["memory_admitted"],
    requires=["memory_admit_policy"],
    emits=["admitted"],
    relates_to=["remember.commit"],
)
class RememberAdmit(Node):
    name = "remember.admit"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control import LcaControlRememberAdmitProvider

        provider = LcaControlRememberAdmitProvider.from_node_config(
            getattr(node, "config", None) or {}
        )
        verdict = provider.admit(
            observation=inputs.get("in_observation"),
            out_port="admit_verdict",
        )
        verdict_art = verdict.get("admit_verdict")
        admitted_flag = False
        if verdict_art is not None and isinstance(verdict_art.content, dict):
            admitted_flag = bool(verdict_art.content.get("admitted"))

        items = _items_from_candidates(inputs.get("in_candidates")) if admitted_flag else []
        out_port = (getattr(node, "config", None) or {}).get("to", "admitted")
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content={"admitted": admitted_flag, "items": items},
                schema_ref="memory.admitted.v1",
            )
        }
