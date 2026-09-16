"""Regression: ``PipelineSafeExecutor`` must populate ``latency_ms``,
``stdout_chars_total``, ``stdout_head`` on every ``step.tool_result.record``.

Bug: ``pipeline_safe_executor.execute`` previously called
``record_step_tool_result`` without those projection fields, so
``stdout_chars_total`` was 0 and ``latency_ms`` was 0 even when the tool
returned real text. Downstream consumers (doctor H7, critic) read the
projection as "empty result" and misread healthy tool runs as failures.

delete-when: ``pipeline_safe_executor`` is folded into
``safe_executor.SimpleSafeExecutor`` (single owner of the projection contract).
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from lca.cognition.body.executor.pipeline_safe_executor import PipelineSafeExecutor
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.result import ToolExecutionError
from lca.contracts.models.team.role.team import (
    CacheConfig,
    RetryPolicy,
    ToolPermissionManifest,
)


@dataclass
class _TextTool:
    """Stub tool whose payload uses the ``text`` key (search / tavily shape)."""

    name: str = "search"
    description: str = "stub"
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    default_timeout_s: int = 30
    body: str = "x" * 4321
    fail: bool = False

    async def execute(self, args: dict[str, Any]) -> Observation:  # type: ignore[override]
        if self.fail:
            raise ToolExecutionError("simulated pipeline failure")
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"text": self.body, "query": "vibe coding"},
        )

    def is_idempotent(self) -> bool:
        return True


@dataclass
class _OutputTool:
    """Stub tool whose payload uses the legacy ``output`` key."""

    name: str = "runCommand"
    description: str = "stub"
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    default_timeout_s: int = 30
    body: str = "x" * 1500

    async def execute(self, args: dict[str, Any]) -> Observation:  # type: ignore[override]
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"output": self.body},
        )

    def is_idempotent(self) -> bool:
        return True


def _permission(*allowed: str) -> ToolPermissionManifest:
    return ToolPermissionManifest(allowed_tools=list(allowed))


def _capture_record_step_tool_result() -> tuple[list[dict[str, Any]], Any]:
    captured: list[dict[str, Any]] = []

    def fake_record_step_tool_result(**kwargs: Any) -> None:
        captured.append(dict(kwargs))

    return captured, fake_record_step_tool_result


async def _execute_with_text_tool() -> list[dict[str, Any]]:
    captured, fake = _capture_record_step_tool_result()
    tool = _TextTool()
    # ADR-0235 / PR-5: plan_ref / scope_ref are typed-injection kwargs.
    executor = PipelineSafeExecutor(
        _permission("search"),
        plan_ref_provider=lambda: "plan_test_search",
        scope_ref_provider=lambda: "turn-text",
    )

    target = "lca.loop.commit.tool_journal.record_step_tool_result"
    with patch(target, side_effect=fake):
        await executor.execute(
            tool,
            {"query": "vibe coding"},
            retry_policy=RetryPolicy(),
            cache_config=CacheConfig(enabled=False),
            invocation_id="inv-text-1",
        )
    return captured


def test_pipeline_safe_executor_projects_text_payload_total_chars() -> None:
    """stdout_chars_total must equal the real text length when payload uses 'text' key."""
    captured = asyncio.run(_execute_with_text_tool())
    assert len(captured) == 1, captured
    payload = captured[0]
    assert payload["tool_name"] == "search"
    assert payload["outcome"] == "ok"
    assert payload["ok"] is True
    assert payload["stdout_chars_total"] == 4321
    assert payload["stdout_head"] == "x" * 2000
    assert payload["latency_ms"] >= 0  # perf_counter() floor


async def _execute_with_output_tool() -> list[dict[str, Any]]:
    captured, fake = _capture_record_step_tool_result()
    tool = _OutputTool()
    executor = PipelineSafeExecutor(
        _permission("runCommand"),
        plan_ref_provider=lambda: "plan_test_output",
        scope_ref_provider=lambda: "turn-output",
    )

    target = "lca.loop.commit.tool_journal.record_step_tool_result"
    with patch(target, side_effect=fake):
        await executor.execute(
            tool,
            {"command": "ls"},
            retry_policy=RetryPolicy(),
            cache_config=CacheConfig(enabled=False),
            invocation_id="inv-output-1",
        )
    return captured


def test_pipeline_safe_executor_projects_output_payload_total_chars() -> None:
    """stdout_chars_total must also read legacy ``output`` key (key list unchanged)."""
    captured = asyncio.run(_execute_with_output_tool())
    assert len(captured) == 1, captured
    payload = captured[0]
    assert payload["stdout_chars_total"] == 1500
    assert payload["stdout_head"] == "x" * 1500  # shorter than 2000 cap


async def _execute_with_failing_tool() -> list[dict[str, Any]]:
    captured, fake = _capture_record_step_tool_result()
    tool = _TextTool(fail=True)
    executor = PipelineSafeExecutor(
        _permission("search"),
        plan_ref_provider=lambda: "plan_test_fail",
        scope_ref_provider=lambda: "turn-fail",
    )

    target = "lca.loop.commit.tool_journal.record_step_tool_result"
    with patch(target, side_effect=fake), suppress(ToolExecutionError):
        await executor.execute(
            tool,
            {"query": "x"},
            retry_policy=RetryPolicy(),
            cache_config=CacheConfig(enabled=False),
            invocation_id="inv-fail-1",
        )
    return captured


def test_pipeline_safe_executor_records_latency_ms_on_failure() -> None:
    """Exception path must still emit latency_ms (existed in record but never populated)."""
    captured = asyncio.run(_execute_with_failing_tool())
    assert len(captured) == 1, captured
    payload = captured[0]
    assert payload["outcome"] == "failure"
    assert payload["ok"] is False
    assert payload["latency_ms"] >= 0
