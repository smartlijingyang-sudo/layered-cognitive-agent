"""ArtifactState 4 状态机（ADR-0068 §一 + ADR-0074 §三裁剪 + tracker §18）。

ADR-0068 §一 8 状态 → ADR-0074 §三裁剪到 4 状态：

旧 8 状态（tracker §18.1）：
- DRAFT / PARSED / DECLARED / VERIFIED / STAGED / ACTIVE / QUIESCING /
  RETIRED + ROLLED_BACK

新 4 状态（PR-8）：
- DRAFT / VERIFIED / ACTIVE / RETIRED

裁剪说明：
- PARSED / DECLARED → fold to DRAFT（VERIFIED 的子步骤）
- STAGED → fold to ACTIVE（staging 是 deploy mode，非独立状态）
- QUIESCING → fold to ACTIVE（quiescing 是 ACTIVE 的退出协议，非独立状态）
- ROLLED_BACK → fold to RETIRED（rollback 是 RETIRED 的子分支）

PR-8 阶段：4 状态 enum + 合法迁移矩阵 + InvalidStateTransition exception。
完整 ArtifactController + CapabilityArtifact 在 PR-8 stage 2 / 阶段 B 落地。
"""

from __future__ import annotations

from enum import Enum


class ArtifactState(str, Enum):
    """Artifact 4 状态机（PR-8 + ADR-0074 §三裁剪）。

    字符串值稳定（journal / plan_ref / journal_record 序列化）；新增状态
    必须经 ADR 批准（C6 改闭集必 ADR）。

    状态语义：

    - ``DRAFT`` —— artifact 刚创建，未校验
    - ``VERIFIED`` —— descriptor / signature / dependency 校验通过
    - ``ACTIVE`` —— runtime 中可消费（已挂载 + 已发布）
    - ``RETIRED`` —— 不可逆终止（artifact 退役 / rollback）
    """

    DRAFT = "draft"
    VERIFIED = "verified"
    ACTIVE = "active"
    RETIRED = "retired"


# 合法迁移矩阵（PR-8 + ADR-0068 §一）：
# - DRAFT → VERIFIED（校验通过）
# - VERIFIED → ACTIVE（promote / mount）
# - VERIFIED → DRAFT（修订：重新校验）
# - ACTIVE → RETIRED（退役 / rollback）
# - RETIRED → terminal（不可逆；不接受任何迁移）
LEGAL_TRANSITIONS: frozenset[tuple[ArtifactState, ArtifactState]] = frozenset(
    {
        (ArtifactState.DRAFT, ArtifactState.VERIFIED),
        (ArtifactState.VERIFIED, ArtifactState.ACTIVE),
        (ArtifactState.VERIFIED, ArtifactState.DRAFT),  # 修订
        (ArtifactState.ACTIVE, ArtifactState.RETIRED),
    }
)


def is_legal_transition(source: ArtifactState, target: ArtifactState) -> bool:
    """``source`` → ``target`` 是否合法迁移。"""
    return (source, target) in LEGAL_TRANSITIONS


def all_states() -> tuple[ArtifactState, ...]:
    """全部状态（按 enum 顺序）。"""
    return tuple(ArtifactState)


def parse_artifact_state(value: object) -> ArtifactState:
    """字符串 / 枚举 → ArtifactState。"""
    if isinstance(value, ArtifactState):
        return value
    if isinstance(value, str):
        try:
            return ArtifactState(value)
        except ValueError as exc:
            raise ValueError(
                f"unknown artifact state {value!r}; valid: {[s.value for s in ArtifactState]}"
            ) from exc
    raise TypeError(f"artifact state must be str or ArtifactState, got {type(value).__name__}")


__all__ = [
    "LEGAL_TRANSITIONS",
    "ArtifactState",
    "all_states",
    "is_legal_transition",
    "parse_artifact_state",
]
