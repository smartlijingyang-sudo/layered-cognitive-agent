"""DecisionClassifier Protocol（ADR-0074）。

将硬编码的 ``build_decision_from_response`` 提取为可插拔 Protocol。
默认实现将原生 function-calling 映射到 USE_TOOL / DELEGATE / RESPOND；
profile 可通过 ``ctx.provide("decision_classifier", ...)`` 注入自替换。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.llm import LLMResponse


@runtime_checkable
class DecisionClassifier(Protocol):
    """Classify LLMResponse into Decision.

    ADR-0074: Extract hard-coded build_decision_from_response into pluggable Protocol.
    Default implementation maps native function-calling to USE_TOOL / DELEGATE / RESPOND.
    Profile can replace via ctx.provide("decision_classifier", ...).
    """

    def classify(self, response: LLMResponse) -> Decision:
        """Classify LLM response into a Decision."""
        ...


__all__ = ["DecisionClassifier"]
