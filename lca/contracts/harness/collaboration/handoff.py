"""Durable ownership handoff facts for delegated Agent work."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentHandoff:
    handoff_id: str
    task_id: str
    from_agent: str
    to_agent: str
    state_ref: str
    summary: str = ""

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.handoff_id,
                self.task_id,
                self.from_agent,
                self.to_agent,
                self.state_ref,
            )
        ):
            raise ValueError("handoff identity fields must not be empty")
        if self.from_agent == self.to_agent:
            raise ValueError("handoff requires distinct owners")


__all__ = ["AgentHandoff"]
