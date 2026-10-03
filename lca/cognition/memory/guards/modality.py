"""摄入模态门控：过滤反事实、举例假设与反讽反话，防止非真实事实污染长期记忆。"""

from __future__ import annotations

import re
from enum import StrEnum


class ModalityResult(StrEnum):
    ADMIT_FACT = "admit_fact"
    HYPOTHETICAL_DROP = "hypothetical_drop"
    SARCASM_DROP = "sarcasm_drop"
    COUNTERFACTUAL_DROP = "counterfactual_drop"


# 假设、虚拟、举例词模式
_HYPOTHETICAL_PATTERNS = [
    re.compile(r"比如(你|我|他|有一个)?"),
    re.compile(r"打个比方"),
    re.compile(r"举个例子"),
    re.compile(r"假(设|如|若)"),
    re.compile(r"如果.*?(将来|以后|要是)"),
    re.compile(r"角色扮演"),
    re.compile(r"设想一下"),
    re.compile(r"写个?(小说|故事)"),
]

# 反讽、反话模式
_SARCASM_PATTERNS = [
    re.compile(r"[\(（].*?反讽.*?[\)）]"),
    re.compile(r"才怪[！!]?"),
    re.compile(r"我最爱.*?加班"),
    re.compile(r"我(太|真)?喜欢.*?被(骂|老板骂|责备)"),
]


def filter_ingestion_modality(text: str) -> ModalityResult:
    """分析输入文本的语气模态。

    对于举例、假设、反事实或反讽表达，返回对应的 DROP 判定；
    对于真实确定的事实，返回 ADMIT_FACT。
    """
    clean_text = text.strip()
    if not clean_text:
        return ModalityResult.HYPOTHETICAL_DROP

    # 1. 检查反讽反话
    for pattern in _SARCASM_PATTERNS:
        if pattern.search(clean_text):
            return ModalityResult.SARCASM_DROP

    # 2. 检查虚拟假设与举例
    for pattern in _HYPOTHETICAL_PATTERNS:
        if pattern.search(clean_text):
            return ModalityResult.HYPOTHETICAL_DROP

    return ModalityResult.ADMIT_FACT
