"""Presentation plane — value types for the run narrative.

This module defines the *immutable* data structures that represent
what actually happened during an agent run, structured for UI rendering.

Design principles:
    - Frozen dataclasses (value semantics, safe to diff/share)
    - No projection logic here (pure data)
    - Turn = one reasoning → action → observation cycle
    - Artifact = first-class product of the run
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

# ── Phase / State enums ─────────────────────────────────────


class PhaseKind(str, Enum):
    """Turn phase — drives SSE reasoning block boundaries."""

    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    ANSWER = "answer"
    IDLE = "idle"


class ToolLifecycleState(str, Enum):
    """Explicit tool lifecycle states — state machine, no shortcuts.

    Transitions:
        STARTED → RUNNING → SUCCEEDED | FAILED
        STARTED → DENIED
    """

    STARTED = "started"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"


# ── Tool Phase ──────────────────────────────────────────────


@dataclass(frozen=True)
class ToolPhase:
    """One tool invocation within a turn.

    ``plugin_state`` is the *complete* state for UI rendering —
    never truncated, never a preview.
    """

    invocation_id: str
    tool_name: str
    wire_name: str = ""
    identifier: str = ""
    api_name: str = ""
    state: ToolLifecycleState = ToolLifecycleState.STARTED
    arguments_full: dict[str, Any] = field(default_factory=dict)
    plugin_state: dict[str, Any] = field(default_factory=dict)
    files: tuple[dict[str, Any], ...] = ()
    started_at: float = 0.0
    ended_at: float | None = None
    error: str = ""
    stdout_buffer: str = ""
    stderr_buffer: str = ""
    latency_ms: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            ToolLifecycleState.SUCCEEDED,
            ToolLifecycleState.FAILED,
            ToolLifecycleState.DENIED,
        }

    @property
    def duration_ms(self) -> int:
        if self.ended_at is not None and self.started_at:
            return int((self.ended_at - self.started_at) * 1000)
        return self.latency_ms

    def evolve(self, **changes: Any) -> ToolPhase:
        """Return a new ToolPhase with the given fields changed."""
        return replace(self, **changes)


# ── Turn ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Turn:
    """One reasoning→action→observation cycle within a run.

    A turn corresponds to one LLM call's worth of activity:
    reasoning text → decision → tool call(s) → observation.

    The key insight: LobeHub renders each reasoning block separately,
    interleaved with tool cards. This structure makes that natural.
    """

    index: int
    step: int = 0
    phase: PhaseKind = PhaseKind.IDLE
    reasoning_text: str = ""
    reasoning_started_at: float | None = None
    reasoning_ended_at: float | None = None
    answer_text: str = ""
    tool_phases: tuple[ToolPhase, ...] = ()
    decision_action: str = ""
    decision_tool_name: str = ""

    @property
    def reasoning_duration_ms(self) -> int:
        if self.reasoning_started_at and self.reasoning_ended_at:
            return int((self.reasoning_ended_at - self.reasoning_started_at) * 1000)
        return 0

    @property
    def has_tools(self) -> bool:
        return len(self.tool_phases) > 0

    @property
    def active_tool_count(self) -> bool:
        return sum(1 for t in self.tool_phases if not t.is_terminal)

    def evolve(self, **changes: Any) -> Turn:
        return replace(self, **changes)


# ── Artifact ────────────────────────────────────────────────


@dataclass(frozen=True)
class Artifact:
    """First-class product of the run.

    Every file produced by any tool invocation becomes an Artifact.
    URL is *always* absolute (resolved by ArtifactRegistry).
    """

    id: str
    name: str
    mime_type: str
    size_bytes: int
    url: str
    previewable: bool = False
    produced_by: str = ""  # invocation_id

    def evolve(self, **changes: Any) -> Artifact:
        return replace(self, **changes)


# ── TurnSnapshot ────────────────────────────────────────────


@dataclass(frozen=True)
class TurnSnapshot:
    """Complete, immutable view of the run's presentation state.

    This is the *single source of truth* for what the UI should show.
    The DiffProjector computes the diff between consecutive snapshots
    to produce SSE chunks.

    Design: frozen dataclass → pure value → safe to diff/share/cache.
    """

    turns: tuple[Turn, ...] = ()
    current_turn_index: int = -1
    finished: bool = False
    finished_at: float | None = None
    status: str = "running"  # running | completed | failed
    final_output: str = ""
    steps_total: int = 0
    error: str = ""
    artifacts: tuple[Artifact, ...] = ()
    prompt_tokens: int = 0
    completion_tokens: int = 0
    started_at: float = 0.0

    @property
    def current_turn(self) -> Turn | None:
        if 0 <= self.current_turn_index < len(self.turns):
            return self.turns[self.current_turn_index]
        return None

    @property
    def tool_calls_total(self) -> int:
        return sum(len(t.tool_phases) for t in self.turns)

    @property
    def open_tool_count(self) -> int:
        """Tools that started but haven't reached terminal state."""
        count = 0
        for t in self.turns:
            for tp in t.tool_phases:
                if not tp.is_terminal:
                    count += 1
        return count

    def evolve(self, **changes: Any) -> TurnSnapshot:
        return replace(self, **changes)

    def replace_turn(self, index: int, turn: Turn) -> TurnSnapshot:
        """Return a new snapshot with the turn at ``index`` replaced."""
        turns = list(self.turns)
        if index < len(turns):
            turns[index] = turn
        return self.evolve(turns=tuple(turns))

    def append_turn(self, turn: Turn) -> TurnSnapshot:
        """Return a new snapshot with ``turn`` appended."""
        return self.evolve(
            turns=(*self.turns, turn),
            current_turn_index=len(self.turns),
        )
