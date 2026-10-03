"""Memory Tact Firewall — 表达分寸防火墙与声带契约（禁显摆/高敏感记忆隔离）。

核心职责：
1. 敏感记忆隔离：亲人去世、严重疾病、经济变故等高敏感记忆，在无关轮次（查天气/写代码等）100% 遮蔽，仅在用户直接提问时放行。
2. 声带契约（禁显摆）：严禁在回答中出现“我记得你说过……”、“据长期记忆库记录……”等监控感/邀功式套话，提倡自然融入。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from lca.cognition.memory.types import SemanticClaim

# 敏感语义关键词字典
_SENSITIVE_KEYWORDS: tuple[str, ...] = (
    "去世",
    "逝世",
    "癌症",
    "重病",
    "肿瘤",
    "破产",
    "欠债",
    "丧偶",
    "身故",
    "家庭变故",
    "离异",
    "病史",
    "绝症",
    "死",
)

# 显摆套话正则
_SHOWOFF_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"我记得你说过"),
    re.compile(r"我记得你提过"),
    re.compile(r"根据我的(?:长期)?记忆库(?:记录)?(?:，)?"),
    re.compile(r"正如您之前提到的(?:，)?"),
    re.compile(r"正如你之前提到的(?:，)?"),
    re.compile(r"据(?:我的)?记忆(?:库)?记录(?:，)?"),
    re.compile(r"回溯我们过去的对话(?:，)?"),
)

# 直接询问意图关键词
_DIRECT_INQUIRY_KEYWORDS: tuple[str, ...] = (
    "提过",
    "说过",
    "变故",
    "去世",
    "逝世",
    "亲人",
    "健康",
    "病史",
    "家境",
    "家里",
    "隐私",
    "之前提",
    "以前说",
)


class MemoryTactFirewall:
    """表达分寸防火墙：执行敏感信息上下文遮蔽与显摆套话清洗。"""

    def __init__(self, memories: Sequence[SemanticClaim | str] | None = None) -> None:
        self._memories: list[SemanticClaim | str] = list(memories or [])

    def filter_for_prompt(
        self,
        user_intent: str,
        memories: Sequence[SemanticClaim | str] | None = None,
    ) -> list[str]:
        """根据当前用户意图过滤出安全、得体的记忆文本供 Prompt 组装。

        - 若用户意图与高敏感记忆无直接关联，严格 100% 抑制高敏感条目；
        - 若用户直接主动询问（如“我提过家里变故吗”），放行相关敏感条目；
        - 普通低敏感记忆正常放行。
        """
        candidates = list(memories if memories is not None else self._memories)
        is_direct = self._is_direct_inquiry(user_intent)

        safe_results: list[str] = []
        for item in candidates:
            text = self._to_text(item)
            sensitive = self._is_sensitive(item, text)
            if sensitive and not is_direct:
                # 无关上下文严格抑制
                continue
            safe_results.append(text)

        return safe_results

    def contains_showoff_phrase(self, text: str) -> bool:
        """检测文本是否包含‘我记得你说过’等监控感显摆套话。"""
        return any(pattern.search(text) is not None for pattern in _SHOWOFF_PATTERNS)

    def sanitize_response(self, text: str) -> str:
        """清洗文本中的显摆套话，转换为自然流畅的客观表达。"""
        cleaned = text
        for pattern in _SHOWOFF_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip()
        # 清理多余的前导逗号或空白
        cleaned = re.sub(r"^[，,、\s]+", "", cleaned)
        return cleaned

    def _is_sensitive(self, item: Any, text: str) -> bool:
        """判断记忆条目是否属于高敏感范畴。"""
        if isinstance(item, SemanticClaim) and getattr(item, "sensitivity", None) == "high":
            return True
        return any(kw in text for kw in _SENSITIVE_KEYWORDS)

    def _is_direct_inquiry(self, user_intent: str) -> bool:
        """判断用户输入是否为对过往敏感历史的直接询问。"""
        intent = user_intent.lower()
        return any(kw in intent for kw in _DIRECT_INQUIRY_KEYWORDS)

    def _to_text(self, item: SemanticClaim | str) -> str:
        """转换条目为纯文本形式。"""
        if isinstance(item, SemanticClaim):
            return item.claim
        return str(item)


__all__ = ["MemoryTactFirewall"]
