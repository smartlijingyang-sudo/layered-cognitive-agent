"""Composable LLM resiliency adapters without changing the agent loop.

A model call belongs to the Think primitive. Provider resiliency therefore wraps
``LLMAdapter`` at the L0 seam rather than adding a loop phase, gateway branch,
or mutable retry state. ``RetryingLLMAdapter`` retries one already-selected
provider after safe availability failures; ``FailoverLLMAdapter`` then moves to
the next Profile-selected provider only when the candidate's bounded retries are
exhausted. Neither wrapper retries after stream content is visible.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.llm_errors import LLMUnavailableError


@dataclass(frozen=True)
class LLMRetryPolicy:
    """Bounded, candidate-local retry policy selected by a Profile.

    ``max_attempts`` includes the initial provider call. Backoff is exponential
    from ``initial_backoff_seconds`` and optionally capped. A zero initial delay
    is valid for deterministic test or low-latency deployments.
    """

    max_attempts: int = 1
    initial_backoff_seconds: float = 0.0
    max_backoff_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("LLM retry max_attempts must be positive")
        if self.initial_backoff_seconds < 0:
            raise ValueError("LLM retry initial_backoff_seconds must be non-negative")
        if self.max_backoff_seconds is not None and self.max_backoff_seconds < 0:
            raise ValueError("LLM retry max_backoff_seconds must be non-negative")

    def delay_for_retry(self, retry_index: int) -> float:
        """Return the bounded exponential delay before retry number ``retry_index``.

        The first retry has index zero. Callers only request a delay after an
        availability failure and before another attempt.
        """

        if retry_index < 0:
            raise ValueError("LLM retry index must be non-negative")
        delay: float = float(self.initial_backoff_seconds * (2**retry_index))
        cap = self.max_backoff_seconds
        if cap is not None and delay > cap:
            return cap
        return delay


class RetryingLLMAdapter(LLMAdapter):
    """Retry one LLMAdapter before its caller considers provider failover.

    Retry eligibility shares the same transport/provider classification as the
    outer fallback adapter. Cancellation, invalid requests, and errors after a
    visible streaming event always propagate unchanged. The adapter keeps no
    mutable request state, so each call remains safe to compose in an immutable
    runtime binding.
    """

    def __init__(
        self,
        adapter: LLMAdapter,
        policy: LLMRetryPolicy,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._adapter = adapter
        self._policy = policy
        self._sleep = sleep

    @property
    def policy(self) -> LLMRetryPolicy:
        """Return the immutable retry policy for diagnostics and tests."""

        return self._policy

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Retry a completion only for bounded availability failures."""

        for attempt in range(self._policy.max_attempts):
            try:
                return await self._adapter.complete(prompt, **kwargs)
            except Exception as error:
                if not self._may_retry(error, attempt):
                    raise
                await self._sleep(self._policy.delay_for_retry(attempt))
        raise RuntimeError("LLM retry exhausted without an adapter result")  # pragma: no cover

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        """Retry a stream only before any event becomes visible to the caller."""

        for attempt in range(self._policy.max_attempts):
            emitted = False
            try:
                async for event in self._adapter.stream(prompt, **kwargs):
                    emitted = True
                    yield event
                return
            except Exception as error:
                if emitted or not self._may_retry(error, attempt):
                    raise
                await self._sleep(self._policy.delay_for_retry(attempt))
        raise RuntimeError("LLM retry exhausted without a stream result")  # pragma: no cover

    def _may_retry(self, error: Exception, attempt: int) -> bool:
        return attempt < self._policy.max_attempts - 1 and is_availability_error(error)


@dataclass(frozen=True)
class LLMFailoverCandidate:
    """One ordered, already-configured LLM adapter candidate."""

    name: str
    adapter: LLMAdapter

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("LLM failover candidate name must not be empty")


class FailoverLLMAdapter(LLMAdapter):
    """Try ordered LLM adapters after safe-to-retry provider failures.

    The wrapper deliberately does not retry programming errors, malformed
    requests, or cancellations. Streaming can safely switch only before the
    first event: after output has become visible, replaying the request could
    duplicate text or tool-call argument deltas, so the original error is
    propagated unchanged.
    """

    def __init__(self, candidates: Sequence[LLMFailoverCandidate]) -> None:
        ordered = tuple(candidates)
        if not ordered:
            raise ValueError("FailoverLLMAdapter requires at least one candidate")
        names = tuple(candidate.name for candidate in ordered)
        if len(set(names)) != len(names):
            raise ValueError("LLM failover candidate names must be unique")
        self._candidates = ordered

    @property
    def candidate_names(self) -> tuple[str, ...]:
        """Expose the fixed selection order for diagnostics and tests."""

        return tuple(candidate.name for candidate in self._candidates)

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Complete through the first available candidate in configured order."""

        for index, candidate in enumerate(self._candidates):
            try:
                return await candidate.adapter.complete(prompt, **kwargs)
            except Exception as exc:
                if not self._may_fail_over(exc, index):
                    raise
        raise RuntimeError("LLM failover exhausted without an adapter result")  # pragma: no cover

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        """Stream through fallbacks only while no provider output was exposed."""

        for index, candidate in enumerate(self._candidates):
            emitted = False
            try:
                async for event in candidate.adapter.stream(prompt, **kwargs):
                    emitted = True
                    yield event
                return
            except Exception as exc:
                if emitted or not self._may_fail_over(exc, index):
                    raise
        raise RuntimeError("LLM failover exhausted without a stream result")  # pragma: no cover

    def _may_fail_over(self, error: Exception, index: int) -> bool:
        return index < len(self._candidates) - 1 and self.is_availability_error(error)

    @staticmethod
    def is_availability_error(error: Exception) -> bool:
        """Backward-compatible access to the shared retry/failover classifier."""

        return is_availability_error(error)


def is_availability_error(error: Exception) -> bool:
    """Return whether an exception is a provider/transport availability fault.

    HTTP client implementations across OpenAI-compatible providers do not share
    one concrete exception tree. The stable cross-client signals are LCA's
    unavailable error, standard transport exceptions, and an optional integer
    ``status_code``. Configuration and request-shape errors remain fail-closed
    on the selected primary provider.
    """

    if isinstance(error, (LLMUnavailableError, TimeoutError, ConnectionError, OSError)):
        return True
    status_code = getattr(error, "status_code", None)
    return isinstance(status_code, int) and (
        status_code in {401, 403, 408, 409, 425, 429} or status_code >= 500
    )


__all__ = [
    "FailoverLLMAdapter",
    "LLMFailoverCandidate",
    "LLMRetryPolicy",
    "RetryingLLMAdapter",
    "is_availability_error",
]
