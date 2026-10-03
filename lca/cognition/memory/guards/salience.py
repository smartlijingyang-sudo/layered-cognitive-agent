"""显著性门控：评估记忆候选的新颖性、复用价值与稳定性，防止单次偶发事件过度泛化为偏好。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SalienceVerdict:
    admitted: bool
    reason: str
    salience_score: float


_CASUAL_ONE_OFF_REGEX = re.compile(
    r"(周末|昨天|今天|刚才|上周|前几天).*?(去|吃|玩|看|听)了?(一次|个)?"
)

_EXPLICIT_PREFERENCE_REGEX = re.compile(
    r"(一贯|总是|从不|必须|喜欢|偏好|习惯|坚持|讨厌|厌恶|不要|严禁)"
)


class SalienceGate:
    """显著性评估门控。"""

    def evaluate(self, task: str, candidate: dict[str, Any]) -> SalienceVerdict:
        """评估该条记忆候选是否允许入库。"""
        category = str(candidate.get("category", "")).lower()

        # 对于偏好类 (preference)，严格检查是否由单次偶发事件无端跃迁
        if category == "preference":
            # 如果原文带有显式长效偏好词，允许准入
            if _EXPLICIT_PREFERENCE_REGEX.search(task):
                return SalienceVerdict(
                    admitted=True,
                    reason="explicit_preference_statement",
                    salience_score=1.0,
                )

            # 如果原文明显是单次偶发事件，且无偏好强化词，拒绝晋升为偏好
            if _CASUAL_ONE_OFF_REGEX.search(task):
                return SalienceVerdict(
                    admitted=False,
                    reason="single_casual_action_not_preference",
                    salience_score=0.3,
                )

        # 默认正常事实放行
        confidence = float(candidate.get("confidence", 0.8))
        return SalienceVerdict(
            admitted=True,
            reason="normal_admit",
            salience_score=confidence,
        )
