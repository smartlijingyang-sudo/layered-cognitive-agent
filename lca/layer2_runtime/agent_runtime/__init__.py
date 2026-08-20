"""LobeHub AgentRuntime semantics on LCA L2 (orchestration contract).

CognitiveRuntime implements the outer step loop; L1 ``llm_turn`` + ``llm_result``
implement ``call_llm`` and ``llm_result`` phases. The chat UI reads Journal SSE
from ``GET /runs/{id}/live`` (see docs/specs/run-live.md).
"""

from lca.layer2_runtime.agent_runtime.phases import AgentPhase

__all__ = [
    "AgentPhase",
]
