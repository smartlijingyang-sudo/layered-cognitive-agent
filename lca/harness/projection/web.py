"""conversation + activity projections for the web gateway."""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.session import SessionEvent


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
        return state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return dict(state)
