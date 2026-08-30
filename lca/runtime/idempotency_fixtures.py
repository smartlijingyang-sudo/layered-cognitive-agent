"""In-memory idempotency storage used only by explicit runtime fixtures."""

from __future__ import annotations

from lca.contracts.protocols.journal.idempotency import IdempotencyClaim, IdempotencyStore


class InMemoryFixtureIdempotencyStore(IdempotencyStore):
    """Provide deterministic process-local idempotency for isolated fixtures.

    Production composition must inject a durable ``IdempotencyStore`` through
    ``ProductionRuntimeDeps``. This implementation intentionally scopes claims
    to one process so unit and end-to-end fixtures can observe repeat effects
    without requiring persistent infrastructure.
    """

    def __init__(self) -> None:
        self._claims: dict[tuple[str, str], dict[str, object]] = {}

    async def claim(self, plan_ref: str, idempotency_key: str) -> IdempotencyClaim:
        key = (plan_ref, idempotency_key)
        record = self._claims.get(key)
        if record is None:
            self._claims[key] = {"status": "in_progress", "receipt": None}
            return IdempotencyClaim(status="new")
        if record["status"] == "completed":
            return IdempotencyClaim(status="completed", receipt=record["receipt"])
        return IdempotencyClaim(status="in_progress")

    async def complete(self, plan_ref: str, idempotency_key: str, receipt: object) -> None:
        key = (plan_ref, idempotency_key)
        if key in self._claims:
            self._claims[key] = {"status": "completed", "receipt": receipt}


__all__ = ["InMemoryFixtureIdempotencyStore"]
