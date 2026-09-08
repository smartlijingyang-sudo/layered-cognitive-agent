"""call_llm node — call OpenAICompatAdapter directly with a prompt string.

Fusion refactor (2026-09-08, second pass): no factory resolution.
call_llm imports OpenAICompatAdapter directly. No provider_kind,
no adapter_factory, no provider_ref. Configuration is just port
renames + optional kwargs forwarded to the adapter.

Inputs are kept minimal: this node receives a TEXT artifact
(`prompt`) and returns a MESSAGE artifact (assistant response).
Prompt assembly is NOT this node's responsibility — it lives in
the model-visible / think sub-graph (a dedicated prompt_assemble
node that flattens system/history/messages into a string).

Boundary:
  - call_llm   : prompt string  -> LLMAdapter -> assistant message
  - prompt_assemble : message list + system + history -> prompt string
                       (lives in the think / model-visible sub-graph)
  - LcaAdapters are imported directly (no factory in node.config).

Reads env (per LCA convention): LLM_API_KEY / LLM_MODEL / LLM_BASE_URL.
"""

from __future__ import annotations

import asyncio

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_message

# Direct LCA import — no factory, no registry.
from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter


@node(
    id="call_llm",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Call OpenAICompatAdapter.complete(prompt) and return the assistant "
        "message. The prompt string is built upstream (by prompt_assemble "
        "or a sub-graph dedicated to prompt construction); this node only "
        "bridges prompt <-> adapter."
    ),
    inputs=[PortInfo("prompt", kind=PortKind.TEXT, required=False)],
    outputs=[PortInfo("response", kind=PortKind.MESSAGE)],
    provides=["llm_response"],
    requires=["prompt_string"],
    consumes=[],
    emits=["llm_call"],
    relates_to=["prompt_assemble", "parse_decision"],
)
class CallLLM(Node):
    """prompt: str  ->  OpenAICompatAdapter  ->  assistant message."""

    name = "call_llm"

    def execute(self, node, inputs):
        out_port = node.config.get("to", "response")
        prompt_a = inputs.get("prompt") or inputs.get(node.config.get("from", "prompt"))
        prompt = prompt_a.content if prompt_a else ""

        # Forward any node.config kwargs to the adapter constructor
        # (e.g. model=, api_key=, base_url=). Default: read from env.
        adapter_kwargs = dict(node.config.get("adapter_kwargs", {}) or {})
        adapter = OpenAICompatAdapter(**adapter_kwargs)

        # adapter.complete is async; bridge to sync.
        response = asyncio.run(adapter.complete(prompt))
        text = getattr(response, "text", "") or ""
        return {out_port: make_message(text, content=text)}
