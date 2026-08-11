"""Tool lifecycle state machine — explicit, formal, impossible to misuse.

Every tool invocation passes through a well-defined state machine:

    STARTED → RUNNING → SUCCEEDED | FAILED
    STARTED → DENIED

The map tracks all invocations and guarantees that:
    1. No invocation can skip states
    2. Every invocation reaches a terminal state on run completion
    3. Timer/lifecycle data is always available

Design: explicit state machine, not ad-hoc flag tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gateway.presentation.turn_snapshot import (
    ToolLifecycleState,
    ToolPhase,
)

# ── Valid transitions ───────────────────────────────────────

_VALID_TRANSITIONS: dict[ToolLifecycleState, frozenset[ToolLifecycleState]] = {
    ToolLifecycleState.STARTED: frozenset(
        {
            ToolLifecycleState.RUNNING,
            ToolLifecycleState.DENIED,
        }
    ),
    ToolLifecycleState.RUNNING: frozenset(
        {
            ToolLifecycleState.SUCCEEDED,
            ToolLifecycleState.FAILED,
        }
    ),
    ToolLifecycleState.SUCCEEDED: frozenset(),
    ToolLifecycleState.FAILED: frozenset(),
    ToolLifecycleState.DENIED: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a tool lifecycle transition violates the state machine."""


def _validate_transition(current: ToolLifecycleState, target: ToolLifecycleState) -> None:
    if target not in _VALID_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransitionError(
            f"Invalid tool lifecycle transition: {current.value} → {target.value}"
        )


# ── Lifecycle Map ───────────────────────────────────────────


@dataclass
class ToolLifecycleMap:
    """Tracks all tool invocations with explicit state machine semantics.

    This is the *mechanism* that prevents:
        - Timers running forever (close_all forces terminal)
        - Missing tool state (every invocation is tracked)
        - Skipped lifecycle steps (transitions are validated)
    """

    invocations: dict[str, ToolPhase] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)

    def start(
        self,
        invocation_id: str,
        tool_name: str,
        *,
        ts: float = 0.0,
        wire_name: str = "",
        identifier: str = "",
        api_name: str = "",
        arguments_full: dict[str, Any] | None = None,
    ) -> ToolPhase:
        """Register a new tool invocation in STARTED state."""
        phase = ToolPhase(
            invocation_id=invocation_id,
            tool_name=tool_name,
            wire_name=wire_name,
            identifier=identifier,
            api_name=api_name,
            state=ToolLifecycleState.STARTED,
            arguments_full=arguments_full or {},
            started_at=ts,
        )
        self.invocations[invocation_id] = phase
        if invocation_id not in self._order:
            self._order.append(invocation_id)
        return phase

    def update(
        self,
        invocation_id: str,
        **changes: Any,
    ) -> ToolPhase:
        """Update fields of an existing invocation (e.g., stdout_buffer)."""
        phase = self.invocations.get(invocation_id)
        if phase is None:
            raise KeyError(f"Unknown invocation: {invocation_id}")
        updated = phase.evolve(**changes)
        self.invocations[invocation_id] = updated
        return updated

    def transition(
        self,
        invocation_id: str,
        target: ToolLifecycleState,
        *,
        ts: float | None = None,
        error: str = "",
        plugin_state: dict[str, Any] | None = None,
        files: tuple[dict[str, Any], ...] | None = None,
        latency_ms: int = 0,
    ) -> ToolPhase:
        """Transition an invocation to a new state.

        Validates the transition against the state machine.
        Raises InvalidTransitionError on illegal transitions.
        """
        phase = self.invocations.get(invocation_id)
        if phase is None:
            raise KeyError(f"Unknown invocation: {invocation_id}")

        _validate_transition(phase.state, target)

        changes: dict[str, Any] = {"state": target}
        if target in {
            ToolLifecycleState.SUCCEEDED,
            ToolLifecycleState.FAILED,
            ToolLifecycleState.DENIED,
        }:
            changes["ended_at"] = ts or phase.started_at
            changes["error"] = error
            changes["latency_ms"] = latency_ms
        if plugin_state is not None:
            changes["plugin_state"] = plugin_state
        if files is not None:
            changes["files"] = files

        updated = phase.evolve(**changes)
        self.invocations[invocation_id] = updated
        return updated

    def stream_output(
        self,
        invocation_id: str,
        *,
        stdout: str = "",
        stderr: str = "",
    ) -> ToolPhase:
        """Append streaming output to an invocation (RUNNING state)."""
        phase = self.invocations.get(invocation_id)
        if phase is None:
            raise KeyError(f"Unknown invocation: {invocation_id}")
        changes: dict[str, Any] = {}
        if stdout:
            changes["stdout_buffer"] = phase.stdout_buffer + stdout
        if stderr:
            changes["stderr_buffer"] = phase.stderr_buffer + stderr
        if not changes:
            return phase
        updated = phase.evolve(**changes)
        self.invocations[invocation_id] = updated
        return updated

    def close_all(self, ts: float) -> None:
        """Force all non-terminal invocations to terminal state.

        This is the *mechanism guarantee* that no timer runs forever.
        Called at run completion — ensures every tool card gets closed.
        """
        for inv_id, phase in self.invocations.items():
            if phase.is_terminal:
                continue
            self.invocations[inv_id] = phase.evolve(
                state=ToolLifecycleState.FAILED,
                ended_at=ts,
                error="run_finished_before_tool_completed",
            )

    def get_ordered(self) -> list[ToolPhase]:
        """Return invocations in insertion order."""
        return [self.invocations[inv_id] for inv_id in self._order if inv_id in self.invocations]

    def get(self, invocation_id: str) -> ToolPhase | None:
        return self.invocations.get(invocation_id)

    @property
    def open_count(self) -> int:
        return sum(1 for p in self.invocations.values() if not p.is_terminal)

    @property
    def total_count(self) -> int:
        return len(self.invocations)
