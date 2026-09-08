"""assemble_lca_mv node — invoke LCA DefaultModelContextAssembler directly.

Fusion refactor (2026-09-08): removed LcaMvProvider + SessionReaderAdapter
adapter layer. This node now:
  1. Builds a SessionReader from agent_lab artifact inputs (inlined)
  2. Invokes DefaultModelContextAssembler.assemble(session, step)
  3. Emits a manifest artifact shaped like ModelVisibleRequest
"""

from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind

from lca.contracts.protocols.session.model.context import ModelContextAssembler
from lca.infrastructure.session.context.model_context_assembler import (
    DefaultModelContextAssembler,
)


class _ArtifactSessionReader:
    """Minimal SessionReader backed by agent_lab artifact inputs.

    Satisfies SessionReader Protocol structurally:
      derive_messages() -> list[dict]
      request_header()  -> dict | None
      snapshot_events() -> tuple (empty, no event log in agent_lab)
    """

    def __init__(
        self,
        messages: list[dict[str, Any]],
        system: str | None,
        config: dict[str, Any] | None,
        tools: list[dict[str, Any]],
    ) -> None:
        self._messages = messages
        self._system = system
        self._config = config
        self._tools = tools

    def derive_messages(self) -> list[dict[str, Any]]:
        return [dict(m) for m in self._messages]

    def request_header(self) -> dict[str, Any] | None:
        if self._system is None and self._config is None and not self._tools:
            return None
        return {"system": self._system, "config": self._config, "tools": list(self._tools)}

    def snapshot_events(self, from_seq: int = 0, to_seq_exclusive: int | None = None) -> tuple:
        return ()


@node(
    id="assemble_lca_mv",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Build a SessionReader from agent_lab artifacts, invoke LCA "
        "DefaultModelContextAssembler.assemble(), and emit a manifest artifact "
        "shaped like ModelVisibleRequest (messages/system/config/tools)."
    ),
    inputs=[
        PortInfo("messages", kind=PortKind.MESSAGE, required=False),
        PortInfo("system", kind=PortKind.TEXT, required=False),
        PortInfo("config", kind=PortKind.FACT, required=False),
        PortInfo("tools", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("manifest", kind=PortKind.MANIFEST)],
    provides=["lca_model_visible_request"],
    requires=["message_list", "system_prompt"],
    consumes=[],
    emits=["context_manifest"],
    relates_to=["commit_manifest", "merge_messages", "assemble_messages"],
)
class AssembleLcaMv(Node):
    """Wire agent_lab into LCA's DefaultModelContextAssembler directly."""

    name = "assemble_lca_mv"

    def execute(self, node, inputs):
        # 1. Coerce artifact inputs into SessionReader shape.
        msgs_a = inputs.get("messages")
        sys_a = inputs.get("system")
        cfg_a = inputs.get("config")
        tls_a = inputs.get("tools")

        messages: list[dict[str, Any]] = []
        if msgs_a is not None and isinstance(msgs_a.content, list):
            messages = [dict(m) for m in msgs_a.content if isinstance(m, dict)]

        system = sys_a.content if (sys_a and isinstance(sys_a.content, str)) else None
        config = dict(cfg_a.content) if (cfg_a and isinstance(cfg_a.content, dict)) else None
        tools: list[dict[str, Any]] = []
        if tls_a is not None and isinstance(tls_a.content, (list, tuple)):
            tools = [dict(t) for t in tls_a.content if isinstance(t, dict)]

        reader = _ArtifactSessionReader(messages, system, config, tools)

        # 2. Run the real LCA assembler.
        assembler: ModelContextAssembler = DefaultModelContextAssembler()
        step = int(node.config.get("step", 0))
        req = assembler.assemble(reader, step=step)

        # 3. Wrap as agent_lab MANIFEST artifact.
        out_port = node.config.get("to", "manifest")
        return {out_port: Artifact(
            kind=ArtifactKind.MANIFEST,
            content={
                "messages": list(req.messages),
                "system": req.system,
                "config": req.config,
                "tools": list(req.tools),
            },
            schema_ref="context.manifest.v1",
        )}
