"""Turn state machine — transforms journal events into structured turns.

Core responsibility: convert the flat stream of journal events into a
structured sequence of Turns, each with explicit phase boundaries:

    REASONING → TOOL_CALL → REASONING → TOOL_CALL → ... → ANSWER → FINISHED

This is the *mechanism* that solves:
    - "Thinking all in one block" — each LLM call = separate Turn
    - "steps=1" — TurnSnapshot.steps_total from AgentRunFinished
    - "Timer never stops" — lifecycle close_all on FINISHED
    - "</think> leak" — ChannelCleanser preprocesses

Design: pure function evolution.
    build(prev_snapshot, stamped_event) → new_snapshot
    No side effects, no emission logic.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from gateway.presentation.artifact_registry import ArtifactRegistry
from gateway.presentation.tool_lifecycle import (
    InvalidTransitionError,
    ToolLifecycleMap,
    ToolLifecycleState,
)
from gateway.presentation.tool_state_builders import build_state_from_invoked
from gateway.presentation.turn_snapshot import (
    PhaseKind,
    ToolPhase,
    Turn,
    TurnSnapshot,
)
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    LlmCallCompleted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    SandboxOutputDelta,
    StampedEvent,
    StepCompleted,
    StepTextDelta,
    TeamRunFinished,
    TeamRunStarted,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)

_log = logging.getLogger(__name__)

# ── Public API ──────────────────────────────────────────────


class TurnStateMachine:
    """Evolves a TurnSnapshot in response to journal events.

    The machine is stateless — all state lives in the TurnSnapshot
    and ToolLifecycleMap passed in. This makes it trivially testable
    and replayable.
    """

    def __init__(self) -> None:
        self._lifecycle = ToolLifecycleMap()
        self._artifacts = ArtifactRegistry()

    @property
    def lifecycle(self) -> ToolLifecycleMap:
        return self._lifecycle

    @property
    def artifacts(self) -> ArtifactRegistry:
        return self._artifacts

    def build_all(self, events: list[StampedEvent]) -> TurnSnapshot:
        """Process a list of events → final snapshot (convenience for replay)."""
        snapshot = TurnSnapshot()
        for stamped in events:
            snapshot = self.build(snapshot, stamped)
        return snapshot

    def build(self, snapshot: TurnSnapshot, stamped: StampedEvent) -> TurnSnapshot:
        """Process one journal event → new snapshot (pure function)."""
        event = stamped.event
        ts = stamped.ts

        if isinstance(event, AgentRunStarted | TeamRunStarted):
            return self._handle_run_started(snapshot, event, ts)
        if isinstance(event, AgentRunFinished | TeamRunFinished):
            return self._handle_run_finished(snapshot, event, ts)
        if isinstance(event, LlmCallStarted):
            return self._handle_llm_started(snapshot, event, ts)
        if isinstance(event, LlmCallCompleted):
            return self._handle_llm_completed(snapshot, event, ts)
        if isinstance(event, ReasoningDelta):
            return self._handle_reasoning_delta(snapshot, event, ts)
        if isinstance(event, ReasoningCompleted):
            return self._handle_reasoning_completed(snapshot, event, ts)
        if isinstance(event, StepTextDelta):
            return self._handle_step_text(snapshot, event, ts)
        if isinstance(event, StepCompleted):
            return self._handle_step_completed(snapshot, event, ts)
        if isinstance(event, DecisionMade):
            return self._handle_decision(snapshot, event, ts)
        if isinstance(event, ToolStarted):
            return self._handle_tool_started(snapshot, event, ts)
        if isinstance(event, SandboxOutputDelta):
            return self._handle_sandbox_output(snapshot, event, ts)
        if isinstance(event, ToolInvoked):
            return self._handle_tool_invoked(snapshot, event, ts)
        if isinstance(event, ToolDenied):
            return self._handle_tool_denied(snapshot, event, ts)

        return snapshot

    # ── Run lifecycle ───────────────────────────────────────

    def _handle_run_started(
        self, snapshot: TurnSnapshot, event: AgentRunStarted | TeamRunStarted, ts: float
    ) -> TurnSnapshot:
        if snapshot.started_at:
            return snapshot
        return snapshot.evolve(started_at=ts)

    def _handle_run_finished(
        self, snapshot: TurnSnapshot, event: AgentRunFinished | TeamRunFinished, ts: float
    ) -> TurnSnapshot:
        # Force all open tools to terminal state (mechanism guarantee)
        self._lifecycle.close_all(ts)
        # Rebuild turns with finalized tool phases
        snapshot = self._sync_tool_phases(snapshot)

        status = getattr(event, "status", "completed")
        error = getattr(event, "error", "") or ""
        output = getattr(event, "output_text", "") or ""
        steps = getattr(event, "steps", 0) or 0

        return snapshot.evolve(
            finished=True,
            finished_at=ts,
            status=status if status else "completed",
            final_output=output,
            steps_total=steps,
            error=error,
        )

    # ── LLM call ────────────────────────────────────────────

    def _handle_llm_started(
        self, snapshot: TurnSnapshot, event: LlmCallStarted, ts: float
    ) -> TurnSnapshot:
        step = event.step if hasattr(event, "step") else 0
        # If we already have a current turn in ANSWER phase, start a new turn
        current = snapshot.current_turn
        if current is not None and current.phase == PhaseKind.ANSWER:
            new_turn = Turn(
                index=len(snapshot.turns),
                step=step or 0,
                phase=PhaseKind.REASONING,
                reasoning_started_at=ts,
            )
            return snapshot.append_turn(new_turn)

        # If no current turn or current is in a terminal phase, start new
        if current is None or current.phase in {PhaseKind.IDLE}:
            new_turn = Turn(
                index=len(snapshot.turns),
                step=step or 0,
                phase=PhaseKind.REASONING,
                reasoning_started_at=ts,
            )
            return snapshot.append_turn(new_turn)

        # If current turn is in REASONING or TOOL_CALL, this is a continuation
        # but with a new step, so we start a new turn
        if current.step != step and step is not None and current.step < step:
            new_turn = Turn(
                index=len(snapshot.turns),
                step=step or 0,
                phase=PhaseKind.REASONING,
                reasoning_started_at=ts,
            )
            return snapshot.append_turn(new_turn)

        return snapshot

    def _handle_llm_completed(
        self, snapshot: TurnSnapshot, event: LlmCallCompleted, ts: float
    ) -> TurnSnapshot:
        # Track token usage
        return snapshot.evolve(
            prompt_tokens=snapshot.prompt_tokens + (event.prompt_tokens or 0),
            completion_tokens=snapshot.completion_tokens + (event.completion_tokens or 0),
        )

    # ── Reasoning ───────────────────────────────────────────

    def _handle_reasoning_delta(
        self, snapshot: TurnSnapshot, event: ReasoningDelta, ts: float
    ) -> TurnSnapshot:
        current = snapshot.current_turn
        if current is None:
            # No turn yet — create one
            new_turn = Turn(
                index=0,
                step=event.step or 0,
                phase=PhaseKind.REASONING,
                reasoning_text=event.text_delta,
                reasoning_started_at=ts,
            )
            return snapshot.append_turn(new_turn)

        # Append to current turn's reasoning
        updated = current.evolve(
            reasoning_text=current.reasoning_text + event.text_delta,
        )
        if current.reasoning_started_at is None:
            updated = updated.evolve(reasoning_started_at=ts)
        return snapshot.replace_turn(current.index, updated)

    def _handle_reasoning_completed(
        self, snapshot: TurnSnapshot, event: ReasoningCompleted, ts: float
    ) -> TurnSnapshot:
        current = snapshot.current_turn
        if current is None:
            return snapshot
        updated = current.evolve(reasoning_ended_at=ts)
        return snapshot.replace_turn(current.index, updated)

    # ── Step text ───────────────────────────────────────────

    def _handle_step_text(
        self, snapshot: TurnSnapshot, event: StepTextDelta, ts: float
    ) -> TurnSnapshot:
        channel = event.channel or StreamChannel.DECISION.value
        current = snapshot.current_turn
        if current is None:
            return snapshot

        # Defensive: strip orphan </think> from step text
        # (belt-and-suspenders with adapter-level ThinkTagStreamSplitter fix)
        text = _strip_orphan_think_tags(event.text_delta)

        if channel == StreamChannel.ANSWER.value:
            # Transition to ANSWER phase if not already
            if current.phase != PhaseKind.ANSWER:
                updated = current.evolve(
                    phase=PhaseKind.ANSWER,
                    answer_text=current.answer_text + text,
                )
            else:
                updated = current.evolve(
                    answer_text=current.answer_text + text,
                )
            return snapshot.replace_turn(current.index, updated)

        return snapshot

    def _handle_step_completed(
        self, snapshot: TurnSnapshot, event: StepCompleted, ts: float
    ) -> TurnSnapshot:
        # Step completed — no snapshot change needed, just lifecycle tracking
        return snapshot

    # ── Decision ────────────────────────────────────────────

    def _handle_decision(
        self, snapshot: TurnSnapshot, event: DecisionMade, ts: float
    ) -> TurnSnapshot:
        current = snapshot.current_turn
        if current is None:
            return snapshot

        updated = current.evolve(
            decision_action=event.action_type or "",
            decision_tool_name=event.tool_name or "",
        )
        return snapshot.replace_turn(current.index, updated)

    # ── Tool lifecycle ──────────────────────────────────────

    def _handle_tool_started(
        self, snapshot: TurnSnapshot, event: ToolStarted, ts: float
    ) -> TurnSnapshot:
        inv_id = event.invocation_id or ""
        # Parse arguments_preview into full dict
        args_full = _safe_parse_json(event.arguments_preview)

        # Register in lifecycle map
        self._lifecycle.start(
            inv_id,
            event.tool_name,
            ts=ts,
            arguments_full=args_full,
        )

        # Ensure we have a current turn; if in REASONING, transition to TOOL_CALL
        current = snapshot.current_turn
        if current is None:
            new_turn = Turn(
                index=0,
                phase=PhaseKind.TOOL_CALL,
                tool_phases=(),
            )
            snapshot = snapshot.append_turn(new_turn)
            current = snapshot.current_turn

        if current is not None and current.phase != PhaseKind.TOOL_CALL:
            # Transition current turn to TOOL_CALL phase
            current = current.evolve(phase=PhaseKind.TOOL_CALL)
            snapshot = snapshot.replace_turn(current.index, current)

        return self._sync_tool_phases(snapshot)

    def _handle_sandbox_output(
        self, snapshot: TurnSnapshot, event: SandboxOutputDelta, ts: float
    ) -> TurnSnapshot:
        inv_id = event.invocation_id or ""
        if not inv_id:
            return snapshot

        # Update lifecycle map
        try:
            if event.stream == "stderr":
                self._lifecycle.stream_output(inv_id, stderr=event.text_delta)
            else:
                self._lifecycle.stream_output(inv_id, stdout=event.text_delta)
        except KeyError:
            pass

        return self._sync_tool_phases(snapshot)

    def _handle_tool_invoked(
        self, snapshot: TurnSnapshot, event: ToolInvoked, ts: float
    ) -> TurnSnapshot:
        inv_id = event.invocation_id or ""
        if not inv_id:
            return snapshot

        target = ToolLifecycleState.SUCCEEDED if event.ok else ToolLifecycleState.FAILED

        # Build plugin_state using the registry
        plugin_state = build_state_from_invoked(event)

        with contextlib.suppress(KeyError, InvalidTransitionError):
            self._lifecycle.transition(
                inv_id,
                target,
                ts=ts,
                error=event.error or "",
                plugin_state=plugin_state,
                files=tuple(event.files) if event.files else None,
                latency_ms=event.latency_ms or 0,
            )

        # Collect artifacts via registry
        if event.files:
            self._artifacts.register_from_invoked_files(event.files, produced_by=inv_id)

        return self._sync_tool_phases(snapshot)

    def _handle_tool_denied(
        self, snapshot: TurnSnapshot, event: ToolDenied, ts: float
    ) -> TurnSnapshot:
        # ToolDenied doesn't have invocation_id in the current schema,
        # so we handle it as a best-effort
        return snapshot

    # ── Internal helpers ────────────────────────────────────

    def _sync_tool_phases(self, snapshot: TurnSnapshot) -> TurnSnapshot:
        """Sync ToolLifecycleMap state into TurnSnapshot turns."""
        if not snapshot.turns:
            return snapshot

        # Build a map of invocation_id → ToolPhase from lifecycle
        inv_to_phase: dict[str, ToolPhase] = {}
        for inv_id, phase in self._lifecycle.invocations.items():
            inv_to_phase[inv_id] = phase

        # For each turn, update its tool_phases
        new_turns: list[Turn] = []
        for turn in snapshot.turns:
            # Collect tool phases that belong to this turn
            # Heuristic: tools started during this turn's step
            tool_phases = list(turn.tool_phases)
            existing_inv_ids = {tp.invocation_id for tp in tool_phases}

            # Add new invocations that aren't in any turn yet
            for inv_id, phase in inv_to_phase.items():
                if inv_id not in existing_inv_ids and self._tool_belongs_to_turn(phase, turn):
                    tool_phases.append(phase)
                    existing_inv_ids.add(inv_id)

            # Update existing tool phases with latest lifecycle state
            updated_tool_phases = []
            for tp in tool_phases:
                latest = inv_to_phase.get(tp.invocation_id, tp)
                updated_tool_phases.append(latest)

            if tuple(updated_tool_phases) != turn.tool_phases:
                turn = turn.evolve(tool_phases=tuple(updated_tool_phases))
            new_turns.append(turn)

        return snapshot.evolve(turns=tuple(new_turns))

    def _tool_belongs_to_turn(self, phase: ToolPhase, turn: Turn) -> bool:
        """Determine if a tool invocation belongs to a given turn."""
        # If the turn has a step, check if the tool started during that step's window
        # Simple heuristic: tool started after the turn's reasoning started
        if turn.reasoning_started_at and phase.started_at >= turn.reasoning_started_at:
            # Check it's not after the next turn's start
            return True
        # If no reasoning time, assign by index order
        return not turn.tool_phases


# ── Module-level helpers ────────────────────────────────────


def _safe_parse_json(text: str) -> dict[str, Any]:
    """Parse JSON safely, returning empty dict on failure."""
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _strip_orphan_think_tags(text: str) -> str:
    """Strip orphan </think> / <think> tags from step text.

    Defensive filter: the adapter-level ThinkTagStreamSplitter should
    prevent these from entering the journal, but this catches any
    residual dirty data (e.g. old journal replays).
    """
    # Remove orphan close tags (no matching open)
    result = text.replace("</think>", "")
    # Remove orphan open tags (no matching close)
    result = result.replace("<think>", "")
    return result
