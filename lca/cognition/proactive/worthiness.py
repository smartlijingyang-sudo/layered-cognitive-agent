# -*- coding: utf-8 -*-
"""WorthinessGate：主动消息裁决门（纯函数，可测）。

决策矩阵（按序，首个命中即返回）：

1. 凭证红线：content 命中凭证模式 → REJECTED（整条拒绝，调用方记 warning）。
   对齐 ADR-0260 §5④：脱敏写入制造"记下了完整事实"的幻觉，比不记更危险。
2. 用户明确要求/触发（requested=True）→ DELIVER_CHAT，回发起上下文。
   对齐 side-chat 隔离：产出回原上下文。
3. 未被要求：
   a. 例行（is_routine）或无实质新信息（not is_novel）→ SILENT（合法默认项）；
   b. 值得打断（worth_interrupting）→ DELIVER_CHAT；
   c. 内容依赖记忆但无记忆源 → DELIVER_QUIET + 标注"未经检索"
     （对齐 ADR-0260 C2：不许在无记忆源时假装记得）；
   d. 其余 → DELIVER_QUIET（安静面）。

muse 思想注记：fail-closed 只用在可精确判定的地方——
凭证模式是精确可判定的，所以 REJECTED；"值得打断"不可机械判定，
所以默认走安静面而非聊天（fail-open + 显式分流，不误杀也不打扰）。
"""

from __future__ import annotations

import re

from lca.contracts.models.proactive.worthiness import (
    ProactiveRequest,
    VerdictKind,
    WorthinessVerdict,
)

# 凭证模式：精确可判定的红线。命中即整条拒绝，不做脱敏改写。
_CREDENTIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|pwd)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(bearer\s+[A-Za-z0-9\-._~+/]+=*)"),
    re.compile(r"\b(sk-[A-Za-z0-9]{8,})"),
    re.compile(r"(?i)\b(mnemonic|private[_-]?key)\b\s*[:=]"),
)


def _contains_credential(content: str) -> bool:
    return any(p.search(content) is not None for p in _CREDENTIAL_PATTERNS)


def decide(request: ProactiveRequest) -> WorthinessVerdict:
    """对一次主动消息请求做纯函数裁决。"""
    content = request.message.content

    # 1. 凭证红线（fail-closed：精确可判定）
    if _contains_credential(content):
        return WorthinessVerdict(
            kind=VerdictKind.REJECTED,
            reason="内容命中凭证模式，整条拒绝（ADR-0260 §5④）",
        )

    # 2. 用户明确要求/触发 → 必达
    if request.requested:
        return WorthinessVerdict(
            kind=VerdictKind.DELIVER_CHAT,
            reason="用户明确触发，必达并回发起上下文",
        )

    # 3a. 例行或无新信息 → 静默（合法默认项）
    if request.is_routine or not request.is_novel:
        return WorthinessVerdict(
            kind=VerdictKind.SILENT,
            reason="例行事项或无实质新信息，静默",
        )

    # 3b. 值得打断 → 推聊天
    if request.worth_interrupting:
        return WorthinessVerdict(
            kind=VerdictKind.DELIVER_CHAT,
            reason="实质新信息且值得打断",
        )

    # 3c. 依赖记忆但无记忆源 → 降级安静面 + 标注
    if request.message.requires_memory and not request.has_memory_source:
        return WorthinessVerdict(
            kind=VerdictKind.DELIVER_QUIET,
            reason="内容依赖记忆但无记忆源，降级安静面",
            annotate_unretrieved=True,
        )

    # 3d. 其余 → 安静面
    return WorthinessVerdict(
        kind=VerdictKind.DELIVER_QUIET,
        reason="未达打断阈值，走安静面",
    )


__all__ = ["decide"]
