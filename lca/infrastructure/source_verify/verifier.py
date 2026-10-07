"""Source-aware verifier —— 来源感知校验器（ProvenanceGuard 思想的结构化实现）.

对答案中**点名了来源**的断言做三件事（与论文的五步流水线对应,
其中"找最相关来源"被字面依据定位替代, NLI 语义判断是预留缝）:

1. 引用的来源存在吗? 不存在 → UNRESOLVABLE（指称幻觉,
   cf. ADR-0255 §4.8 "点名而不存在 = 指称幻觉"）.
2. 断言里的数字 / 日期 / 标识符, 是否逐字出现在引用的来源原文里?
   不在 → UNSUPPORTED（论文设计选择②: 严格字面检查）.
3. 字面依据在**别的**已登记来源里, 而不在引用的来源里 →
   CONFLATED（跨来源混同: 事实是对的, 但挂在了错的来源上）.

没有引用来源的断言不 penalize（保守策略: 论文同样宁可漏检, 不乱拦）.
答案级决定由 VerifyMode 决定: OFF 直接 pass; WARN 可疑→needs_review;
ENFORCE 可疑→block（需上游接复核 / 兜底链路）.
"""

from __future__ import annotations

import logging
import re

from lca.contracts.models.cognition.source_verify import (
    ClaimVerdict,
    SourceClaimVerdict,
    VerifyDecision,
    VerifyMode,
)
from lca.infrastructure.source_verify.claims import extract_citations, split_claims
from lca.infrastructure.source_verify.policy import VerifyPolicy
from lca.infrastructure.source_verify.registry import SourceRegistry

_log = logging.getLogger("lca.source_verify")

_LITERAL = re.compile(
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?"  # 日期 2026-10-01 / 2026年10月1日
    r"|\d+(?:\.\d+)?%?"  # 数字（含百分比）
    r"|[A-Za-z0-9_.-]{4,}"  # 标识符（call_id、工单号、版本号等）
)


def _extract_literals(claim: str) -> tuple[str, ...]:
    seen: list[str] = []
    for m in _LITERAL.finditer(claim):
        lit = m.group(0)
        if lit not in seen:
            seen.append(lit)
    return tuple(seen)


class SourceVerifier:
    """对最终答案做来源感知校验."""

    def __init__(self, policy: VerifyPolicy | None = None) -> None:
        self._policy = policy or VerifyPolicy.default()

    @property
    def policy(self) -> VerifyPolicy:
        return self._policy

    def verify(self, answer: str, registry: SourceRegistry) -> VerifyDecision:
        mode = self._policy.mode
        if mode == VerifyMode.OFF or not answer.strip() or not registry:
            return VerifyDecision(decision="pass", verdicts=(), mode=mode)

        verdicts: list[SourceClaimVerdict] = []
        for claim in split_claims(answer):
            cited = extract_citations(claim, registry)
            if not cited:
                continue
            for sid in cited:
                verdicts.append(self._judge_claim(claim, sid, registry))

        bad = [v for v in verdicts if v.verdict != ClaimVerdict.SUPPORTED]
        if not bad:
            decision = "pass"
        elif mode == VerifyMode.ENFORCE:
            decision = "block"
        else:
            decision = "needs_review"
        if bad:
            _log.warning(
                "source_verify: %d/%d cited claims failed (%s)",
                len(bad),
                len(verdicts),
                ",".join(sorted({v.verdict.value for v in bad})),
            )
        return VerifyDecision(decision=decision, verdicts=tuple(verdicts), mode=mode)

    def _judge_claim(
        self, claim: str, cited_id: str, registry: SourceRegistry
    ) -> SourceClaimVerdict:
        hit = registry.get(cited_id)
        if hit is None:
            return SourceClaimVerdict(
                claim=claim,
                verdict=ClaimVerdict.UNRESOLVABLE,
                cited_source_id=cited_id,
                matched_source_id=None,
                reason=f"引用的来源不存在: {cited_id}（指称幻觉）",
            )
        _, content = hit
        literals = _extract_literals(claim)
        missing = [lit for lit in literals if lit not in content]
        if not missing:
            return SourceClaimVerdict(
                claim=claim,
                verdict=ClaimVerdict.SUPPORTED,
                cited_source_id=cited_id,
                matched_source_id=cited_id,
                reason="字面依据全部出现在引用来源中"
                if literals
                else "引用来源存在（断言无可核验字面量）",
            )
        # 字面依据不在引用来源里 —— 看看是不是在别的来源里（跨来源混同）
        for other_id in registry.source_ids():
            if other_id == cited_id:
                continue
            other_hit = registry.get(other_id)
            if other_hit is None:
                continue
            _, other_content = other_hit
            if all(lit in other_content for lit in missing):
                return SourceClaimVerdict(
                    claim=claim,
                    verdict=ClaimVerdict.CONFLATED,
                    cited_source_id=cited_id,
                    matched_source_id=other_id,
                    reason=f"字面依据 {missing} 不在引用来源中, 而在 {other_id} 中",
                )
        return SourceClaimVerdict(
            claim=claim,
            verdict=ClaimVerdict.UNSUPPORTED,
            cited_source_id=cited_id,
            matched_source_id=None,
            reason=f"字面依据 {missing} 在引用来源中找不到",
        )


def verify_final_answer(
    answer: str,
    registry: SourceRegistry,
    policy: VerifyPolicy | None = None,
) -> VerifyDecision:
    """便捷入口: 对最终答案做一次来源校验（默认 WARN, 只告警不拦截）."""
    return SourceVerifier(policy or VerifyPolicy.default()).verify(answer, registry)
