"""Reasoner spine fact envelope (ADR-0194 P1-15).

Think pipeline calls this seam so ``PromptReasoner`` stays pure; infrastructure
``cognitive_emit`` owns ``publish_ep_bound`` routing.

.. deprecated::
    v1 (2026-09-10 spec): think.reason 已拆为 inner_graph (plan/render/complete),
    EP 由节点 config.emit_on_* 声明,driver 自动发。本 seam 函数被 think.reason
    inner_graph 替代,保留仅为兼容老 caller.

delete-when:
    1. 所有 phase graph driver 都走 v2 (NOT v0 GraphAssembler fallback)
    2. 节点级 sub_spec_ref 在 prod profile 落地 (think-subgraph-dev 已用)
    3. think.reason inner_graph 拆解已落地 (本 spec)
    4. 至少 1 个 prod profile 跑通 3 个月,期间无 seam fallback 触发
owner: lca/loop/emit/cognitive/reasoner.py 维护者
validation: 条件 1-3 已满足;条件 4 由 owner 评估
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
