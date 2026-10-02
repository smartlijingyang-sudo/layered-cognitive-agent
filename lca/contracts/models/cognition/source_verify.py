"""Source-aware verification contracts —— 来源感知校验（ProvenanceGuard 思想落地）.

设计来源:
- ProvenanceGuard（Multiverse Computing）: "Getting the Source Right, Not
  Just the Fact" —— agent 答案不仅要事实对, 还要来源挂得对; 核心失败模式
  ``cross-source conflation``（跨来源混同）: 事实是对的, 但归因到了错误的来源.
- Muse 对齐（ADR-0255 §4.4）: 记忆不是字符串, 是**带出生证明的记录**;
  没有 provenance 的记录 = 不可审计的幻觉. 同理: 没有来源身份的工具输出 =
  塌缩成匿名上下文的证据, 事后无法审计"这条断言到底是哪个工具说的".

本文件只定义契约（冻结 dataclass + 枚举）, 不含任何执行逻辑.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class SourceKind(str, Enum):
    """一条证据的来源种类."""

    TOOL = "tool"  # 工具调用输出
    MEMORY = "memory"  # 长期记忆检索
    RETRIEVAL = "retrieval"  # RAG / 向量检索
    USER = "user"  # 用户本轮消息
    SYSTEM = "system"  # 系统 / standing 文件


class VerifyMode(str, Enum):
    """校验层的介入强度."""

    OFF = "off"  # 关闭, 只采集来源, 不校验
    WARN = "warn"  # 只告警: 记录可疑断言, 不拦截答案（默认）
    ENFORCE = "enforce"  # 拦截: 可疑答案走复核 / 兜底


class ClaimVerdict(str, Enum):
    """单条断言的来源裁决."""

    SUPPORTED = "supported"  # 引用的来源真实包含该断言的字面依据
    CONFLATED = "conflated"  # 跨来源混同: 事实在别的来源里, 归因错了
    UNSUPPORTED = "unsupported"  # 引用的来源不支持该断言
    UNRESOLVABLE = "unresolvable"  # 引用的来源不存在（指称幻觉）


@dataclass(frozen=True, slots=True)
class SourceRef:
    """一条证据的稳定来源引用 —— "出生证明"."""

    source_id: str  # 稳定 ID, 如 "tool:call_abc123"; 模型可直接引用
    kind: SourceKind
    label: str  # 人类可读名, 如 "账户记录"; 供"根据X"模式匹配
    tool_name: str | None = None
    call_id: str | None = None
    captured_at: str = ""  # ISO 时间戳, 证据被采集的时间


@dataclass(frozen=True, slots=True)
class SourceClaimVerdict:
    """一条断言的来源裁决明细."""

    claim: str
    verdict: ClaimVerdict
    cited_source_id: str | None  # 答案里点名 / 暗示的来源
    matched_source_id: str | None  # 实际包含字面依据的来源（若找到）
    reason: str


@dataclass(frozen=True, slots=True)
class VerifyDecision:
    """一次答案级来源校验的最终决定."""

    decision: Literal["pass", "needs_review", "block"]
    verdicts: tuple[SourceClaimVerdict, ...]
    mode: VerifyMode
