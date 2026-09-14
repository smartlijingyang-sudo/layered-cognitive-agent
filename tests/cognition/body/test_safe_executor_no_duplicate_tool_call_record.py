"""Regression: ``SimpleSafeExecutor.execute`` must emit ``step.tool_call.record`` exactly once per invocation.

Bug: prior to this fix, ``SimpleSafeExecutor.execute`` called
``record_step_tool_call`` directly AND routed through
``_commit_tool_started`` → ``record_tool_started_observability`` which itself
called ``record_step_tool_call`` again with the same ``invocation_id``. Spine
traces (e.g. ``run_91e7bd5c5850``) showed two ``step.tool_call.record`` events
under one step with identical ``invocation_id`` and arguments.

Fix: split ``record_tool_started_observability`` into a diagnostic-only
helper (``record_tool_started_diagnostic``) and the original
full-bundle helper. ``_commit_tool_started`` now calls the diagnostic-only
variant because the upstream ``execute`` already committed the spine fact.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.team.role.team import CacheConfig, RetryPolicy, ToolPermissionManifest


@dataclass
class _StubTool:
    """Minimal ``Tool`` stub: returns success with payload containing ``output``."""

    name: str = "runCommand"

    async def execute(self, args: dict[str, Any]) -> Observation:  # type: ignore[override]
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"output": "ok", "exit_code": 0},
        )

    def is_idempotent(self) -> bool:
        return True


def _permission() -> ToolPermissionManifest:
    return ToolPermissionManifest(allowed_tools=["runCommand"])


def _capture_publish_ep() -> list[tuple[str, dict[str, Any]]]:
    return []


def _test_publish_ep_factory() -> tuple[list[tuple[str, dict[str, Any]]], Any]:
    captured: list[tuple[str, dict[str, Any]]] = []

    def fake_publish_ep(
        ep: str,
        payload: dict[str, Any],
        *,
        state: Any = None,
        session: Any = None,
        actor: str = "body",
    ) -> None:
        captured.append((ep, dict(payload)))

    return captured, fake_publish_ep


async def _run_execute_once(invocation_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Execute a stub tool once and return captured publish calls."""
    executor = SimpleSafeExecutor(_permission())
    tool = _StubTool()

    captured, fake_publish_ep = _test_publish_ep_factory()

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        await executor.execute(
            tool,
            {"command": "ls"},
            RetryPolicy(),
            CacheConfig(enabled=False),
            invocation_id=invocation_id,
        )

    return captured


def test_safe_executor_emits_step_tool_call_record_exactly_once() -> None:
    """One ``execute`` call → exactly one ``step.tool_call.record`` for that invocation."""
    invocation_id = "inv-dup-test-1"
    captured = asyncio.run(_run_execute_once(invocation_id))

    tool_call_records = [(ep, payload) for ep, payload in captured if ep == "step.tool_call.record"]
    assert len(tool_call_records) == 1, (
        f"expected exactly one step.tool_call.record per execute(), got "
        f"{len(tool_call_records)}: {tool_call_records}"
    )
    _ep, payload = tool_call_records[0]
    assert payload["invocation_id"] == invocation_id
    assert payload["tool_name"] == "runCommand"


def test_safe_executor_emits_step_tool_result_record_exactly_once() -> None:
    """One ``execute`` call → exactly one ``step.tool_result.record`` for that invocation.

    Independent regression — ``record_step_tool_result`` must not also be
    double-emitted. Pinned here so the two seams stay symmetric.
    """
    invocation_id = "inv-dup-test-2"
    captured = asyncio.run(_run_execute_once(invocation_id))

    tool_result_records = [
        (ep, payload) for ep, payload in captured if ep == "step.tool_result.record"
    ]
    assert len(tool_result_records) == 1, (
        f"expected exactly one step.tool_result.record per execute(), got "
        f"{len(tool_result_records)}: {tool_result_records}"
    )
    _ep, payload = tool_result_records[0]
    assert payload["invocation_id"] == invocation_id
    assert payload["outcome"] == "ok"
    assert payload["ok"] is True


def test_diagnostic_helper_does_not_emit_step_tool_call_record() -> None:
    """``record_tool_started_diagnostic`` is diagnostic-only — no spine fact."""

    from lca.cognition.body.emit.tool_journal import (
        record_tool_started_diagnostic,
    )

    captured, fake_publish_ep = _test_publish_ep_factory()

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        record_tool_started_diagnostic(
            tool=_StubTool(),
            args={"command": "ls"},
            invocation_id="inv-diag-test",
        )

    # No spine fact under any name
    spine_facts = [
        (ep, payload)
        for ep, payload in captured
        if ep in ("step.tool_call.record", "step.tool_result.record")
    ]
    assert spine_facts == []


def test_full_observability_helper_still_routes_through_record_step_tool_call() -> None:
    """``record_tool_started_observability`` retains its emit (used by emit_tool_started).

    Locks the ADR-0185 P5 single-track contract — the public wrapper still
    commits ``step.tool_call.record`` for callers that have NOT separately
    routed it.
    """
    from lca.cognition.body.emit.tool_journal import (
        record_tool_started_observability,
    )
    from lca.contracts.models.observability.tool.journal_receipt import (
        tool_started_receipt,
    )

    tool = _StubTool()
    receipt = tool_started_receipt(
        tool_name=tool.name,
        invocation_id="inv-obs-test",
        arguments={"command": "ls"},
        arguments_ref=None,
        idempotency_key="",
    )

    captured, fake_publish_ep = _test_publish_ep_factory()
    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        record_tool_started_observability(tool, {"command": "ls"}, "inv-obs-test", receipt)

    tool_call_records = [ep for ep, _ in captured if ep == "step.tool_call.record"]
    assert len(tool_call_records) == 1
