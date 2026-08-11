"""LobeHub AgentRuntime semantics on LCA L2 (orchestration contract).

CognitiveRuntime implements the outer step loop; L1 ``llm_turn`` + ``llm_result``
implement ``call_llm`` and ``llm_result`` phases. Gateway ``JournalOpenAiProjector``
implements G2A outward streaming.
"""

from lca.layer2_runtime.agent_runtime.phases import (
    G2A_FINISH_REASON,
    LOBEHUB_TEXT_ONLY_MEANS_FINISH,
    AgentPhase,
)

__all__ = [
    "G2A_FINISH_REASON",
    "LOBEHUB_TEXT_ONLY_MEANS_FINISH",
    "AgentPhase",
]
