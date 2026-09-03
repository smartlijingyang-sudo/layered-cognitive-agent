"""Tests for profile-configured LLM provider failover."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest import IsolatedAsyncioTestCase, mock

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.infrastructure.llm_adapter.failover import (
    FailoverLLMAdapter,
    LLMFailoverCandidate,
    LLMRetryPolicy,
    RetryingLLMAdapter,
)
from lca.plugins.think.llm_resolver_seam import (
    Config,
    FallbackConfig,
    RetryConfig,
    setup,
)


class _HttpError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class _Adapter:
    def __init__(
        self,
        *,
        response: LLMResponse | None = None,
        complete_error: Exception | None = None,
        stream_events: tuple[LLMStreamEvent, ...] = (),
        stream_error: Exception | None = None,
    ) -> None:
        self.response = response or LLMResponse(text="ok", model="test")
        self.complete_error = complete_error
        self.stream_events = stream_events
        self.stream_error = stream_error
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
        del prompt, kwargs
        self.complete_calls += 1
        if self.complete_error is not None:
            raise self.complete_error
        return self.response

    async def stream(self, prompt: str, **kwargs: object) -> AsyncIterator[LLMStreamEvent]:
        del prompt, kwargs
        self.stream_calls += 1
        for event in self.stream_events:
            yield event
        if self.stream_error is not None:
            raise self.stream_error


class _SequencedAdapter:
    """Adapter fake whose results differ by attempt."""

    def __init__(
        self,
        *,
        complete_outcomes: list[LLMResponse | Exception] | None = None,
        stream_outcomes: list[tuple[tuple[LLMStreamEvent, ...], Exception | None]] | None = None,
    ) -> None:
        self._complete_outcomes = list(complete_outcomes or [])
        self._stream_outcomes = list(stream_outcomes or [])
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
        del prompt, kwargs
        self.complete_calls += 1
        outcome = self._complete_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def stream(self, prompt: str, **kwargs: object) -> AsyncIterator[LLMStreamEvent]:
        del prompt, kwargs
        self.stream_calls += 1
        events, error = self._stream_outcomes.pop(0)
        for event in events:
            yield event
        if error is not None:
            raise error


class _LlmService:
    def __init__(self) -> None:
        self.registered: tuple[str, object, bool] | None = None

    def register(self, name: str, adapter: object, *, activate: bool = False) -> None:
        self.registered = (name, adapter, activate)


class _PluginContext:
    def __init__(self, service: _LlmService) -> None:
        self._service = service
        self.provided: dict[str, object] = {}

    def require(self, name: str) -> _LlmService:
        assert name == "llm"
        return self._service

    def provide(self, name: str, value: object) -> None:
        self.provided[name] = value


class TestFailoverLLMAdapter(IsolatedAsyncioTestCase):
    async def test_complete_uses_fallback_after_transient_primary_failure(self) -> None:
        primary = _Adapter(complete_error=TimeoutError("provider timed out"))
        expected = LLMResponse(text="fallback answer", model="secondary")
        secondary = _Adapter(response=expected)
        adapter = FailoverLLMAdapter(
            (
                LLMFailoverCandidate("primary", primary),
                LLMFailoverCandidate("secondary", secondary),
            )
        )

        result = await adapter.complete("task")

        self.assertIs(result, expected)
        self.assertEqual(adapter.candidate_names, ("primary", "secondary"))
        self.assertEqual(primary.complete_calls, 1)
        self.assertEqual(secondary.complete_calls, 1)

    async def test_complete_uses_fallback_for_retryable_http_status(self) -> None:
        primary = _Adapter(complete_error=_HttpError(429))
        secondary = _Adapter(response=LLMResponse(text="recovered", model="secondary"))
        adapter = FailoverLLMAdapter(
            (
                LLMFailoverCandidate("primary", primary),
                LLMFailoverCandidate("secondary", secondary),
            )
        )

        result = await adapter.complete("task")

        self.assertEqual(result.text, "recovered")
        self.assertEqual(secondary.complete_calls, 1)

    async def test_complete_does_not_hide_non_availability_failures(self) -> None:
        primary = _Adapter(complete_error=ValueError("invalid request shape"))
        secondary = _Adapter()
        adapter = FailoverLLMAdapter(
            (
                LLMFailoverCandidate("primary", primary),
                LLMFailoverCandidate("secondary", secondary),
            )
        )

        with self.assertRaisesRegex(ValueError, "invalid request shape"):
            await adapter.complete("task")

        self.assertEqual(secondary.complete_calls, 0)

    async def test_stream_uses_fallback_before_any_visible_output(self) -> None:
        primary = _Adapter(stream_error=TimeoutError("provider timed out"))
        completed = LLMStreamEvent(
            type=LLMStreamEventType.COMPLETED,
            response=LLMResponse(text="recovered", model="secondary"),
        )
        secondary = _Adapter(stream_events=(completed,))
        adapter = FailoverLLMAdapter(
            (
                LLMFailoverCandidate("primary", primary),
                LLMFailoverCandidate("secondary", secondary),
            )
        )

        events = [event async for event in adapter.stream("task")]

        self.assertEqual(events, [completed])
        self.assertEqual(primary.stream_calls, 1)
        self.assertEqual(secondary.stream_calls, 1)

    async def test_stream_does_not_duplicate_visible_output_after_failure(self) -> None:
        delta = LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="partial")
        primary = _Adapter(stream_events=(delta,), stream_error=TimeoutError("dropped"))
        secondary = _Adapter()
        adapter = FailoverLLMAdapter(
            (
                LLMFailoverCandidate("primary", primary),
                LLMFailoverCandidate("secondary", secondary),
            )
        )

        received: list[LLMStreamEvent] = []
        with self.assertRaisesRegex(TimeoutError, "dropped"):
            async for event in adapter.stream("task"):
                received.append(event)

        self.assertEqual(received, [delta])
        self.assertEqual(secondary.stream_calls, 0)

    async def test_complete_retries_one_candidate_before_failover(self) -> None:
        expected = LLMResponse(text="recovered locally", model="primary")
        primary = _SequencedAdapter(complete_outcomes=[TimeoutError("first attempt"), expected])
        delays: list[float] = []

        async def record_delay(delay: float) -> None:
            delays.append(delay)

        adapter = RetryingLLMAdapter(
            primary,
            LLMRetryPolicy(max_attempts=2, initial_backoff_seconds=0.25),
            sleep=record_delay,
        )

        result = await adapter.complete("task")

        self.assertIs(result, expected)
        self.assertEqual(primary.complete_calls, 2)
        self.assertEqual(delays, [0.25])

    async def test_exhausted_candidate_retries_before_ordered_failover(self) -> None:
        primary = _SequencedAdapter(
            complete_outcomes=[TimeoutError("first attempt"), TimeoutError("second attempt")]
        )
        fallback = _Adapter(response=LLMResponse(text="fallback answer", model="secondary"))
        adapter = FailoverLLMAdapter(
            (
                LLMFailoverCandidate(
                    "primary",
                    RetryingLLMAdapter(primary, LLMRetryPolicy(max_attempts=2)),
                ),
                LLMFailoverCandidate("secondary", fallback),
            )
        )

        result = await adapter.complete("task")

        self.assertEqual(result.text, "fallback answer")
        self.assertEqual(primary.complete_calls, 2)
        self.assertEqual(fallback.complete_calls, 1)

    async def test_stream_retries_before_any_visible_output(self) -> None:
        completed = LLMStreamEvent(
            type=LLMStreamEventType.COMPLETED,
            response=LLMResponse(text="recovered", model="primary"),
        )
        primary = _SequencedAdapter(
            stream_outcomes=[((), TimeoutError("first attempt")), ((completed,), None)]
        )
        delays: list[float] = []

        async def record_delay(delay: float) -> None:
            delays.append(delay)

        adapter = RetryingLLMAdapter(
            primary,
            LLMRetryPolicy(max_attempts=2, initial_backoff_seconds=0.25),
            sleep=record_delay,
        )

        events = [event async for event in adapter.stream("task")]

        self.assertEqual(events, [completed])
        self.assertEqual(primary.stream_calls, 2)
        self.assertEqual(delays, [0.25])

    async def test_stream_does_not_retry_after_visible_output(self) -> None:
        delta = LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="partial")
        primary = _SequencedAdapter(stream_outcomes=[((delta,), TimeoutError("dropped"))])
        delays: list[float] = []

        async def record_delay(delay: float) -> None:
            delays.append(delay)

        adapter = RetryingLLMAdapter(
            primary,
            LLMRetryPolicy(max_attempts=2, initial_backoff_seconds=0.25),
            sleep=record_delay,
        )

        received: list[LLMStreamEvent] = []
        with self.assertRaisesRegex(TimeoutError, "dropped"):
            async for event in adapter.stream("task"):
                received.append(event)

        self.assertEqual(received, [delta])
        self.assertEqual(primary.stream_calls, 1)
        self.assertEqual(delays, [])

    def test_retry_policy_rejects_invalid_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_attempts"):
            LLMRetryPolicy(max_attempts=0)
        with self.assertRaisesRegex(ValueError, "initial_backoff"):
            LLMRetryPolicy(initial_backoff_seconds=-0.1)
        with self.assertRaisesRegex(ValueError, "max_backoff"):
            LLMRetryPolicy(max_backoff_seconds=-0.1)

    def test_requires_nonempty_unique_candidate_names(self) -> None:
        adapter = _Adapter()
        with self.assertRaisesRegex(ValueError, "at least one"):
            FailoverLLMAdapter(())
        with self.assertRaisesRegex(ValueError, "unique"):
            FailoverLLMAdapter(
                (
                    LLMFailoverCandidate("same", adapter),
                    LLMFailoverCandidate("same", adapter),
                )
            )


class TestFailoverResolverConfiguration(IsolatedAsyncioTestCase):
    async def test_profile_config_wraps_primary_and_fallback_adapters(self) -> None:
        service = _LlmService()
        context = _PluginContext(service)
        primary = _Adapter()
        secondary = _Adapter()
        config = Config(
            default_model="primary-model",
            api_key="primary-key",
            load_dotenv=False,
            retry=RetryConfig(max_attempts=2, initial_backoff_seconds=0.5),
            fallbacks=(FallbackConfig(model="fallback-model"),),
        )

        with (
            mock.patch("lca.infrastructure.llm.config.normalize_llm_environ"),
            mock.patch(
                "lca.infrastructure.llm_adapter.openai_compat.OpenAICompatAdapter",
                side_effect=(primary, secondary),
            ) as adapter_factory,
        ):
            await setup.setup(context, config)

        assert service.registered is not None
        name, adapter, active = service.registered
        self.assertEqual(name, "default")
        self.assertTrue(active)
        self.assertIsInstance(adapter, FailoverLLMAdapter)
        self.assertEqual(adapter.candidate_names, ("primary", "fallback-1"))
        self.assertEqual(adapter_factory.call_count, 2)
        self.assertEqual(adapter_factory.call_args_list[1].kwargs["model"], "fallback-model")
        self.assertEqual(adapter_factory.call_args_list[1].kwargs["api_key"], "primary-key")
        self.assertIsInstance(adapter._candidates[0].adapter, RetryingLLMAdapter)
        primary_retry = adapter._candidates[0].adapter
        assert isinstance(primary_retry, RetryingLLMAdapter)
        self.assertEqual(primary_retry.policy.max_attempts, 2)
        self.assertEqual(primary_retry.policy.initial_backoff_seconds, 0.5)
        self.assertIn("llm_resolver", context.provided)


if __name__ == "__main__":
    import unittest

    unittest.main()
