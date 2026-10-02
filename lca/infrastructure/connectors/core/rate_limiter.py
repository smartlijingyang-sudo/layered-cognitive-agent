"""Sliding-window hard rate limiter for external connectors (INV-05)."""

from __future__ import annotations

import math
import time


class ConnectorRateLimitExceededError(Exception):
    """Raised when an operation exceeds the connector's rate limit window."""

    def __init__(self, service: str, limit: int, retry_after_seconds: int) -> None:
        self.service = service
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Rate limit exceeded for connector '{service}' (limit: {limit} units/min). "
            f"Retry after {retry_after_seconds} seconds (INV-05)."
        )


class SlidingWindowRateLimiter:
    """Enforces per-minute token/unit consumption using a 60-second sliding window."""

    def __init__(self) -> None:
        self._history: dict[str, list[tuple[float, int]]] = {}

    def check_and_consume(
        self,
        service: str,
        units: int,
        limit_per_minute: int = 250,
        now: float | None = None,
    ) -> tuple[bool, int]:
        current_time = now if now is not None else time.time()
        window_start = current_time - 60.0

        records = self._history.get(service, [])
        # Evict records older than 60 seconds
        active_records = [r for r in records if r[0] > window_start]
        self._history[service] = active_records

        current_usage = sum(r[1] for r in active_records)

        if current_usage + units > limit_per_minute:
            # Calculate when enough units will expire
            if active_records:
                earliest_ts = active_records[0][0]
                retry_after = max(1, math.ceil((earliest_ts + 60.0) - current_time))
            else:
                retry_after = 60
            return False, retry_after

        active_records.append((current_time, units))
        return True, 0

    def enforce(
        self,
        service: str,
        units: int,
        limit_per_minute: int = 250,
        now: float | None = None,
    ) -> None:
        allowed, retry_after = self.check_and_consume(
            service, units=units, limit_per_minute=limit_per_minute, now=now
        )
        if not allowed:
            raise ConnectorRateLimitExceededError(
                service=service,
                limit=limit_per_minute,
                retry_after_seconds=retry_after,
            )
