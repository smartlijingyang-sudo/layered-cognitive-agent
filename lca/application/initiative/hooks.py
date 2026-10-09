from collections.abc import Sequence
from typing import Any

from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.contracts.models.initiative.models import (
    InitiativeOffer,
    InitiativeSignal,
)


def derive_transcript_features(
    prior_turns: Sequence[ConversationTurn],
    extra_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive baseline transcript features for the initiative hook.

    Caller override wins: when the caller injected richer features via
    ``RunContext.extra["transcript_features"]`` they are returned as-is
    (ADR-0248 slice 8).  Otherwise a baseline is derived from prior
    turns: per-role counts plus an empty manual-action map.  Pure and
    unit-testable; the run driver is its only consumer.
    """
    if extra_override:
        return dict(extra_override)
    turns = prior_turns or ()
    return {
        "user_turn_count": sum(1 for t in turns if t.role == "user"),
        "assistant_turn_count": sum(1 for t in turns if t.role == "assistant"),
        "manual_action_counts": {},
    }


def evaluate_initiative(transcript_features: dict[str, Any]) -> InitiativeOffer | None:
    """纯函数主动提议钩子。

    根据 ADR-0248 §5.2 规范：
    主动（Initiative）是策略不是人格。
    纯函数读入 transcript 特征统计，单轮至多输出 0 或 1 条高价值建议，
    绝不滥发或造成消息风暴。
    """
    # 1. 检查缺连接器
    missing = transcript_features.get("missing_connectors", [])
    if missing:
        conn = missing[0]
        return InitiativeOffer(
            signal=InitiativeSignal.MISSING_CONNECTOR,
            nudge_message=f"检测到缺少服务连接器 '{conn}'，建议配置连接器以获得更稳定的执行效果。",
        )

    # 2. 检查重复操作第三次
    counts: dict[str, int] = transcript_features.get("manual_action_counts", {})
    for action_name, count in counts.items():
        if count >= 3:
            return InitiativeOffer(
                signal=InitiativeSignal.REPEATED_MANUAL,
                nudge_message=f"检测到动作 '{action_name}' 已重复执行 {count} 次，是否建立自动例程（Routine）？",
                proposed_routine=action_name,
            )

    return None
