"""TerminalOutcome / OutputRef / ResumeCursor / ErrorRef — 终态唯一事实契约（ADR-0077 §决策一）。

Per ADR-0077, Stop phase 与 reducer 折叠后必须产出唯一的 ``TerminalOutcome``
实例。Final user-visible output (text / artifact / stream / structured) is
referenced via ``OutputRef`` discriminated union, never inlined as a string.

Per-kind invariants are enforced in ``TerminalOutcome.__post_init__`` so the
contract fails closed at reducer fold rather than silently at projection
read. Adding a new kind requires ADR supersession of ADR-0077 (宪法 C6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TerminalOutcomeKind(str, Enum):
    """Closed set of terminal outcomes（ADR-0077 §决策一，宪法 C6 闭集）。

    Every non-"继续循环" exit path must map to exactly one of these values.
    """

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    WAITING_INPUT = "waiting_input"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class TextRef:
    """文本片段引用；resolver 按 ``seq`` 从 journal 取回原内容。"""

    text: str = ""
    seq: int = 0
    cursor: str = ""


@dataclass(frozen=True)
class ArtifactRef:
    """Artifact 引用（sandbox file、image 等）。"""

    artifact_id: str = ""
    plan_ref: str = ""
    artifact_kind: str = ""


@dataclass(frozen=True)
class StructuredRef:
    """结构化（JSON-schema）输出引用。"""

    schema_id: str = ""
    value_ref: str = ""


@dataclass(frozen=True)
class StreamRef:
    """流式输出引用（首/末 journal seq + 模型标识）。"""

    first_seq: int = 0
    last_seq: int = 0
    model: str = ""


# Discriminated union tagged by the type itself; resolvers dispatch on
# ``isinstance(ref, (TextRef, ArtifactRef, StructuredRef, StreamRef))``.
OutputRef = TextRef | ArtifactRef | StructuredRef | StreamRef


def _output_ref_kind(ref: OutputRef | None) -> str:
    """Return a stable string discriminator for an OutputRef (or "" for None)."""
    if ref is None:
        return ""
    if isinstance(ref, TextRef):
        return "text"
    if isinstance(ref, ArtifactRef):
        return "artifact"
    if isinstance(ref, StructuredRef):
        return "structured"
    if isinstance(ref, StreamRef):
        return "stream"
    raise TypeError(f"Unknown OutputRef type: {type(ref).__name__}")


@dataclass(frozen=True)
class ResumeCursor:
    """HIL / Approval resume 契约（ADR-0077 + ADR-0078 联合）。"""

    cursor: str = ""
    session_seq: int = 0
    approval_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.cursor, str) or not self.cursor:
            raise ValueError("resume cursor must be a non-empty string")
        if not isinstance(self.approval_id, str) or not self.approval_id:
            raise ValueError("resume approval_id must be a non-empty string")
        if not isinstance(self.session_seq, int) or isinstance(self.session_seq, bool):
            raise ValueError("resume session_seq must be an integer")
        if self.session_seq < 0:
            raise ValueError("resume session_seq must be non-negative")


@dataclass(frozen=True)
class ErrorRef:
    """错误引用；``kind`` 形如 'crash' | 'approval_timeout' | 'cancel'。"""

    kind: str = ""
    message: str = ""
    source_ref: str = ""  # journal ref 到引发错误的事件


@dataclass(frozen=True)
class TerminalOutcome:
    """终态唯一事实（ADR-0077 §决策一）。

    由 Reducer 折叠 StopDecision / artifact closure 产出；任何 phase 不得
    直接构造（ADR-0077 §决策二）。所有用户可见 result 字段从本实例 +
    对应 projection 派生（ADR-0077 §决策三）。
    """

    kind: TerminalOutcomeKind
    stop_reason: str
    final_output_ref: TextRef | ArtifactRef | StructuredRef | StreamRef | None = None
    artifact_refs: tuple[ArtifactRef, ...] = ()
    error_ref: ErrorRef | None = None
    resume_cursor: ResumeCursor | None = None
    plan_ref: str = ""
    journal_seq_end: int = 0

    def __post_init__(self) -> None:
        _validate_terminal_outcome_invariants(self)

    def output_ref_kind(self) -> str:
        """Stable string discriminator for the bound OutputRef (or "" for None)."""
        return _output_ref_kind(self.final_output_ref)


def _validate_terminal_outcome_invariants(outcome: TerminalOutcome) -> None:
    """Enforce ADR-0077 per-kind invariants at construction time."""
    kind = outcome.kind

    if kind is TerminalOutcomeKind.COMPLETED:
        if outcome.final_output_ref is None:
            raise ValueError("TerminalOutcome(COMPLETED) requires final_output_ref")
    elif kind is TerminalOutcomeKind.FAILED:
        if outcome.error_ref is None:
            raise ValueError("TerminalOutcome(FAILED) requires error_ref")
    elif kind is TerminalOutcomeKind.WAITING_INPUT:
        if outcome.resume_cursor is None:
            raise ValueError("TerminalOutcome(WAITING_INPUT) requires resume_cursor")
    elif (
        kind in (TerminalOutcomeKind.CANCELED, TerminalOutcomeKind.DEGRADED)
        and outcome.final_output_ref is None
        and outcome.error_ref is None
    ):
        raise ValueError(f"TerminalOutcome({kind.value}) requires final_output_ref or error_ref")

    if not outcome.plan_ref:
        raise ValueError("TerminalOutcome.plan_ref must be non-empty for replay")
    if outcome.journal_seq_end < 0:
        raise ValueError("TerminalOutcome.journal_seq_end must be non-negative")


__all__ = [
    "ArtifactRef",
    "ErrorRef",
    "OutputRef",
    "ResumeCursor",
    "StreamRef",
    "StructuredRef",
    "TerminalOutcome",
    "TerminalOutcomeKind",
    "TextRef",
]
