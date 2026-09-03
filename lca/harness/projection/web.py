"""conversation + activity projections for the web gateway."""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent
from lca.contracts.observability.ssot import is_terminal_run_status

# ADR-0098 D4: terminal Statuses 命中后 ActivityProjection.view 增加 terminal=True 标记
# 仅字典多一字段,旧 client 只读 status/turn/error 不受影响
_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "canceled", "waiting_input"})


class ConversationProjection:
    key = "conversation"
    version = 1

    def init(self) -> dict[str, Any]:
        return {"messages": [], "last_assistant_message": None}

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        if event.type == "message.accepted.v1":
            state["messages"].append(
                {
                    "role": event.data.get("role"),
                    "content_ref": event.data.get("content_ref"),
                    "seq": event.seq,
                }
            )
        if event.type == "session.checkpoint.v1" and event.data.get("answer"):
            state["last_assistant_message"] = event.data["answer"]
        return state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "messages": list(state["messages"]),
            "last_assistant_message": state["last_assistant_message"],
        }


class TaskProjection:
    """Whole-value task view derived from the session event stream."""

    key = "task"
    version = 1

    def init(self) -> dict[str, Any]:
        return {
            "task_id": None,
            "session_id": None,
            "objective": None,
            "profile": None,
            "status": "created",
            "last_seq": -1,
        }

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        if event.seq <= state.get("last_seq", -1):
            return state
        if event.type in {"TaskCreated", "task.created.v1"}:
            state.update(
                {
                    "task_id": event.data.get("task_id"),
                    "session_id": event.session_id,
                    "objective": event.data.get("objective"),
                    "profile": event.data.get("profile"),
                    "status": "created",
                }
            )
        elif event.type in {"turn.started.v1", "task.started.v1"}:
            if not is_terminal_run_status(state.get("status", "")):
                state["status"] = "working"
        elif event.type in {"turn.ended.v1", "task.completed.v1"}:
            state["status"] = event.data.get("status", "completed")
        elif event.type in {"run.failed.v1", "task.failed.v1"}:
            state["status"] = "failed"
        state["last_seq"] = event.seq
        return state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state)


class ActivityProjection:
    key = "activity"
    version = 1

    def init(self) -> dict[str, Any]:
        return {"status": "idle", "turn": 0, "error": None}

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        if event.type == "session.created.v1":
            state["status"] = "idle"
        elif event.type == "message.accepted.v1":
            state["status"] = "working"
        elif event.type == "turn.started.v1":
            state["turn"] = event.data.get("turn", state["turn"])
            state["status"] = "working"
        elif event.type == "turn.ended.v1":
            reason = event.data.get("reason", "completed")
            mapping = {
                "completed": "completed",
                "aborted": "canceled",
                "error": "failed",
                "budget": "failed",
                "waiting_input": "waiting_input",
            }
            state["status"] = mapping.get(reason, reason)
        elif event.type == "session.checkpoint.v1":
            state["status"] = event.data.get("status") or state["status"]
            state["error"] = event.data.get("error")
        elif event.type == "command.rejected.v1":
            state["error"] = event.data.get("reason")
        # ADR-0098 D4: 终止状态命中时打 terminal=True 标记
        if state.get("status") in _TERMINAL_STATUSES:
            state["terminal"] = True
        return state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state)
