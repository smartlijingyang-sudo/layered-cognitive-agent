"""Running-operation index for Agent Gateway reconnect (ADR-0200 §3.2)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RunningOperationStore(Protocol):
    """Durable index: topic → active run_id (+ HIL idempotency keys)."""

    async def insert(
        self,
        *,
        run_id: str,
        topic_id: str,
        agent_id: str,
        assistant_message_id: str | None,
        scope: str,
    ) -> None: ...

    async def get_latest_for_topic(self, topic_id: str) -> dict | None: ...

    async def record_answer_key(self, run_id: str, idempotency_key: str) -> None: ...

    async def delete(self, run_id: str) -> None: ...


__all__ = ("RunningOperationStore",)
