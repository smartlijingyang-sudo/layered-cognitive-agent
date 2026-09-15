"""CurrentReasonerPrompt DTO — explicit DI replacement for the deleted
``_current_reasoner_prompt`` ContextVar (spec section H).

ADR-0175 D3 / ADR-0185 PR-4 history: this dataclass used to live behind a
ContextVar; the ContextVar machinery (bind/get/reset) is deleted in Task 5.
Reasoner constructs the dataclass locally and passes it through
``llm.complete(..., reasoner_prompt=prompt)`` to the model-visible hook
adapter; the hook reads ``prompt.system_prompt_text``.

Ownership: Reasoner constructs (post-render); LLM-boundary hook reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.cognition.prompt_assembly import PromptTrace
from lca.contracts.models.core.perceive.perception import ContextManifest


@dataclass(frozen=True)
class CurrentReasonerPrompt:
    """Reasoner passes this to the LLM boundary; hook reads ``system_prompt_text``.

    ``system_prompt_text`` 为空时,hook 走降级分支(空 system 归一为 absent)。

    所有权:Reasoner 在 prompt 渲染完成时构造,显式传进
    ``llm.complete(reasoner_prompt=...)``;LLM 边界
    (:class:`ModelVisibleHook`)只读 —— 把 ``system_prompt_text`` 写进
    ``SpineLlmRequestHeaderPayload.system``,不修改本对象。

    ``prompt_trace`` / ``context_manifest`` 默认 None,保留既有 4 标量
    构造;传递时携带完整 :class:`PromptTrace`(section trace + skill ids)
    与本 turn 的 :class:`ContextManifest`,使 spine event 可重建
    skill / prompt 装配(ADR-0167 D3/D4)。
    """

    step_id: str
    template_id: str
    selector_decision_path: str
    system_prompt_text: str
    prompt_trace: PromptTrace | None = None
    context_manifest: ContextManifest | None = None


__all__ = ["CurrentReasonerPrompt"]
