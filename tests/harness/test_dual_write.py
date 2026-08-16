"""Tests for shadow dual-write executor (spec §B.3)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from lca.harness.command.dual_write import ShadowConfig, ShadowExecutor
from lca.harness.diagnostics.normalizer import ResultNormalizer


class TestShadowExecutor:
    """Shadow mode: runs legacy + new path, compares results."""

    def test_shadow_runs_both_paths(self) -> None:
        """Shadow executor runs legacy and new, returns legacy result."""
        legacy_result = MagicMock(
            status="completed",
            answer="hello",
            tool_calls=[],
            llm_calls=1,
            error=None,
            journal_events=[],
        )
        legacy_fn = AsyncMock(return_value=legacy_result)
        new_fn = AsyncMock(return_value=MagicMock())

        async def _test() -> None:
            executor = ShadowExecutor()
            result = await executor.execute_shadow(
                legacy_fn=legacy_fn,
                new_fn=new_fn,
            )
            assert legacy_fn.await_count == 1
            assert new_fn.await_count == 1
            assert result is legacy_result

        asyncio.run(_test())

    def test_shadow_logs_divergence(self) -> None:
        """When results diverge, compare reports divergence."""
        legacy_result = MagicMock(
            status="completed",
            answer="hello",
            tool_calls=[],
            llm_calls=1,
            error=None,
            journal_events=[],
        )
        new_snapshot = MagicMock()
        new_snapshot.values = {"activity": {"status": "failed"}, "conversation": {}}

        normalizer = ResultNormalizer()
        executor = ShadowExecutor(normalizer=normalizer)
        report = executor.compare(legacy_result, new_snapshot, journal=[])
        # Divergence should be detected (status: completed vs failed)
        assert len(report.divergences) > 0

    def test_shadow_new_path_timeout_returns_legacy(self) -> None:
        """New path timeout should not block legacy result."""
        legacy_result = MagicMock(
            status="completed",
            answer="legacy",
            tool_calls=[],
            llm_calls=1,
            error=None,
            journal_events=[],
        )
        legacy_fn = AsyncMock(return_value=legacy_result)

        async def _slow_new() -> None:
            await asyncio.sleep(1.0)

        async def _test() -> None:
            executor = ShadowExecutor(config=ShadowConfig(timeout_seconds=0.05))
            result = await executor.execute_shadow(
                legacy_fn=legacy_fn, new_fn=_slow_new,
            )
            assert result is legacy_result

        asyncio.run(_test())

    def test_shadow_new_path_error_returns_legacy(self) -> None:
        """New path error should not break legacy result."""
        legacy_result = MagicMock(
            status="completed",
            answer="legacy",
            tool_calls=[],
            llm_calls=1,
            error=None,
            journal_events=[],
        )
        legacy_fn = AsyncMock(return_value=legacy_result)

        async def _failing_new() -> None:
            raise RuntimeError("new path boom")

        async def _test() -> None:
            executor = ShadowExecutor()
            result = await executor.execute_shadow(
                legacy_fn=legacy_fn, new_fn=_failing_new,
            )
            assert result is legacy_result

        asyncio.run(_test())

    def test_compare_matching_results_no_divergence(self) -> None:
        """Matching results should produce no divergences."""
        legacy_result = MagicMock(
            status="completed",
            answer="hello",
            tool_calls=[],
            llm_calls=2,
            error=None,
            journal_events=[],
        )
        new_snapshot = MagicMock()
        new_snapshot.values = {
            "activity": {"status": "completed"},
            "conversation": {"last_assistant_message": "hello"},
        }

        journal_events = [
            MagicMock(type="model.completed.v1"),
            MagicMock(type="model.completed.v1"),
        ]

        executor = ShadowExecutor()
        report = executor.compare(legacy_result, new_snapshot, journal=journal_events)
        assert len(report.divergences) == 0
