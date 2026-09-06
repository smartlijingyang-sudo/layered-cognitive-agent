"""Reasoner spine fact envelope (ADR-0194 P1-15).

Think pipeline calls this seam so ``PromptReasoner`` stays pure; infrastructure
``cognitive_emit`` owns ``publish_ep_bound`` routing.
"""

from __future__ import annotations

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import Reasoner
from lca.infrastructure.session.emit.cognitive_emit import (
    run_reasoner_generate_thoughts_with_spine_facts,
)


async def run_reasoner_with_spine_facts(reasoner: Reasoner, state: AgentState) -> LLMResponse:
    """Run one reasoner turn with prompt-assembler and reasoner spine EPs."""
    return await run_reasoner_generate_thoughts_with_spine_facts(reasoner, state)


__all__ = ["run_reasoner_with_spine_facts"]
