"""Replay-safe skills projection derived only from Session events."""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent


class SkillsProjection:
    key = "skills"
    version = 1

    def init(self) -> dict[str, Any]:
        return {"catalog_digest": "", "available": [], "loaded": [], "user_invocations": []}

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        if event.type == "skill.catalog.published.v1":
            state["catalog_digest"] = str(event.data["digest"])
            state["available"] = list(event.data["entries"])
        elif event.type == "skill.loaded.v1":
            state["loaded"].append(
                {
                    "skill_id": event.data["skill_id"],
                    "content_hash": event.data["content_hash"],
                    "invocation": event.data["invocation"],
                    "seq": event.seq,
                }
            )
        elif event.type == "skill.user_invoked.v1":
            state["user_invocations"].append(event.data["skill_id"])
        return state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "catalog_digest": state["catalog_digest"],
            "available": list(state["available"]),
            "loaded": list(state["loaded"]),
            "user_invocations": list(state["user_invocations"]),
        }
