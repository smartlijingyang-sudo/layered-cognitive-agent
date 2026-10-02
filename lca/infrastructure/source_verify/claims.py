"""Claim splitting + citation extraction —— 断言切分与来源引用提取.

启发式实现, 无需 LLM:
- 按句号/问号/感叹号/换行切分答案为断言;
- 从断言中提取两类来源引用:
  1. 显式标记 ``[source:<source_id>]``（模型引用工具结果首行 marker 时产生）;
  2. "根据X / 来自X / 依据X / 按照X"模式, X 经 registry.resolve_label 解析.

LLM 语义级支持度判断（NLI）是预留的协议缝, 不在本文件实现.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.infrastructure.source_verify.registry import SourceRegistry

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])|[\n]+")
_EXPLICIT_MARKER = re.compile(r"\[source:([^\]]+)\]")
_LABEL_CITE = re.compile(r"(?:根据|来自|依据|按照|引自)([^，。！？,.;:：\s]{1,24})")


def split_claims(answer: str) -> tuple[str, ...]:
    """把答案切成断言, 去空去重保序."""
    parts = _SENTENCE_SPLIT.split(answer)
    claims: list[str] = []
    seen: set[str] = set()
    for p in parts:
        c = p.strip().strip("[]")
        if len(c) >= 4 and c not in seen:
            seen.add(c)
            claims.append(c)
    return tuple(claims)


def extract_citations(claim: str, registry: SourceRegistry) -> tuple[str, ...]:
    """从一条断言中提取它引用的 source_id（去重保序）."""
    found: list[str] = []
    for m in _EXPLICIT_MARKER.finditer(claim):
        sid = m.group(1).strip()
        if sid and sid not in found:
            found.append(sid)
    for m in _LABEL_CITE.finditer(claim):
        sid = registry.resolve_label(m.group(1))
        if sid and sid not in found:
            found.append(sid)
    return tuple(found)
