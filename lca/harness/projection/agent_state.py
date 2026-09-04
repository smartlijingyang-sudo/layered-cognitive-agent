"""AgentStateProjection - materializes AgentState from journal events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent
from lca.contracts.models.core.budget import Budget
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState


@dataclass
class AgentStateProjection:
    """Projection that reconstructs AgentState from session events.

    This projection folds journal events into an AgentState, allowing
    the agent state to be recovered from the event log.
    """

    key = "agent_state"
    version = 1

    def init(self) -> AgentState:
        """Initialize an empty AgentState."""
        return AgentState(
            trace_id="",
            task="",
            budget=Budget(),
            schema_version="1.0",
            working_memory={},
            retrieved_context=[],
            step=0,
            checkpoints=[],
            status=TaskStatus.WORKING,
            extra={},
            agent_role="",
            from_role="",
            team_awareness=None,
            history=[],
            final_output=None,
            last_error=None,
            active_template=None,
            activated_skills=[],
        )

    def apply(self, state: AgentState, event: SessionEvent) -> AgentState:
        """Apply a session event to update the agent state.

        Args:
            state: Current agent state
            event: Session event to apply

        Returns:
            Updated agent state
        """
        event_type = event.type
        data = event.data

        if event_type == "session.created.v1":
            # Initialize from session creation
            state.trace_id = event.session_id
            if "profile" in data:
                state.extra["profile"] = data["profile"]

        elif event_type == "turn.started.v1":
            # Reset step counter for new turn
            if "turn" in data:
                state.extra["current_turn"] = data["turn"]

        elif event_type == "step.ended.v1":
            # Increment step counter
            if "step" in data:
                state.step = data["step"] + 1

        elif event_type == "session.checkpoint.v1":
            # Update status from checkpoint
            status_str = data.get("status", "working")
            state.status = _parse_status(status_str)
            # ADR-0158 决策 四:AgentState.final_output 字段已删除。
            # answer 文本走 TerminalOutcome.final_output_ref 通道
            # (projection 反序列化仅折叠 status / error)。
            if data.get("error"):
                state.last_error = data["error"]

        elif event_type == "model.completed.v1":
            # Track LLM completion
            if "response" in data:
                state.extra["last_model_response"] = data["response"]

        return state

    def view(self, state: AgentState) -> dict[str, Any]:
        """Convert AgentState to a serializable view.

        Args:
            state: Agent state

        Returns:
            Dictionary representation of the state
        """
        return {
            "trace_id": state.trace_id,
            "task": state.task,
            "step": state.step,
            "status": state.status.value,
            # ADR-0158 决策 四:final_output 不再是 agentState 字段;
            # view 不导出该键;调用方改读 TerminalOutcome.final_output_ref。
            "last_error": state.last_error,
            "working_memory_keys": list(state.working_memory.keys()),
            "history_length": len(state.history),
            "extra_keys": list(state.extra.keys()),
        }


def _parse_status(status_str: str) -> TaskStatus:
    """Parse status string to TaskStatus enum."""
    status_map = {
        "working": TaskStatus.WORKING,
        "completed": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
        "canceled": TaskStatus.CANCELED,
        "paused": TaskStatus.PAUSED,
        "input_required": TaskStatus.INPUT_REQUIRED,
        "waiting_input": TaskStatus.INPUT_REQUIRED,
    }
    return status_map.get(status_str.lower(), TaskStatus.WORKING)
