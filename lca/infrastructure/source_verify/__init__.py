"""Source-aware verification —— 来源感知校验（ProvenanceGuard 思想落地）.

"Getting the Source Right, Not Just the Fact": agent 答案不仅要事实对,
还要来源挂得对. 本包提供:

- :class:`VerifyPolicy` —— 介入强度（OFF / WARN / ENFORCE, 默认 WARN）;
- :class:`SourceRegistry` —— 本轮所有证据来源的登记簿（来源身份一路贯穿）;
- :func:`verify_final_answer` —— 对最终答案做来源校验, 逐断言裁决 + 答案级决定.

Muse 对齐（ADR-0255 §4.4）: 没有 provenance 的记录 = 不可审计的幻觉.
工具输出从产生的一刻起就带上稳定 source_id, 绝不塌缩成匿名上下文.
"""

from lca.contracts.models.cognition.source_verify import (
    ClaimVerdict,
    SourceClaimVerdict,
    SourceKind,
    SourceRef,
    VerifyDecision,
    VerifyMode,
)
from lca.infrastructure.source_verify.claims import extract_citations, split_claims
from lca.infrastructure.source_verify.policy import VerifyPolicy
from lca.infrastructure.source_verify.registry import (
    SourceRegistry,
    ensure_registry,
    get_registry,
    source_marker,
)
from lca.infrastructure.source_verify.verifier import (
    SourceVerifier,
    verify_final_answer,
)

__all__ = [
    "ClaimVerdict",
    "SourceClaimVerdict",
    "SourceKind",
    "SourceRef",
    "SourceRegistry",
    "SourceVerifier",
    "VerifyDecision",
    "VerifyMode",
    "VerifyPolicy",
    "ensure_registry",
    "extract_citations",
    "get_registry",
    "source_marker",
    "split_claims",
    "verify_final_answer",
]
