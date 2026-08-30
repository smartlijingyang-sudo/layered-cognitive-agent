"""Default evidence policy —— ADR-0065 L5 / L8 默认决策。

默认规则:
- classify: 由 hint 直接采用;hint 缺失时按关键字 + media_type 启发式提升
  分类(``text/plain`` / ``application/json`` 中含 ``password`` / ``secret``
  / ``api_key`` → RESTRICTED)。
- retention: 由 hint 采用;hint 缺失时 PUBLIC/INTERNAL 默认 RUN_DEFAULT,
  RESTRICTED 默认 LONG(CONFIDENTIAL 默认 PERMANENT)。
- should_inline: RESTRICTED / CONFIDENTIAL 永不内联;PUBLIC/INTERNAL ≤64 KiB
  内联;>64 KiB 走 evidence ref。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.observability.evidence import Classification, EvidencePolicy, RetentionClass

_DEFAULT_INLINE_THRESHOLD_BYTES = 64 * 1024

_RESTRICTED_KEYWORDS: tuple[bytes, ...] = (
    b"password",
    b"secret",
    b"api_key",
    b"apikey",
    b"private_key",
    b"access_token",
    b"refresh_token",
    b"bearer ",
)


@dataclass(slots=True)
class DefaultEvidencePolicy(EvidencePolicy):
    """默认 policy 决策器(0065 L5 / L8)。"""

    inline_threshold_bytes: int = _DEFAULT_INLINE_THRESHOLD_BYTES
    extra_restricted_keywords: tuple[bytes, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.inline_threshold_bytes <= 0:
            raise ValueError("inline_threshold_bytes must be > 0")

    # ── EvidencePolicy 契约 ──────────────────────────────────────

    def classify(
        self,
        payload: bytes,
        *,
        hint: Classification | None = None,
        media_type: str = "application/octet-stream",
    ) -> Classification:
        if hint is not None:
            return hint
        # 启发式:关键字触发升级
        lowered = payload.lower()
        keywords = _RESTRICTED_KEYWORDS + self.extra_restricted_keywords
        if any(kw in lowered for kw in keywords):
            return Classification.RESTRICTED
        # 默认按 media_type 区分
        if media_type.startswith("application/json") or media_type.startswith("text/"):
            return Classification.INTERNAL
        return Classification.INTERNAL

    def retention(
        self,
        payload: bytes,
        *,
        hint: RetentionClass | None = None,
    ) -> RetentionClass:
        if hint is not None:
            return hint
        return RetentionClass.RUN_DEFAULT

    def should_inline(
        self,
        payload: bytes,
        *,
        classification: Classification,
    ) -> bool:
        if classification in (Classification.RESTRICTED, Classification.CONFIDENTIAL):
            return False
        return len(payload) <= self.inline_threshold_bytes


__all__ = ["DefaultEvidencePolicy"]
