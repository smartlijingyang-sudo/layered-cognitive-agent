"""Regression: ``step.tool_result.record.latency_ms`` must carry the real duration.

``SimpleSafeExecutor.execute`` measured the invocation window for its sibling
fact (``body.tool.execute.end`` gets ``_elapsed_ms``) but never forwarded a
duration to ``record_step_tool_result``, so the model-visible tool result took
the ``latency_ms: int = 0`` default. In ``run_5490e7c8a76c`` all 10 journal
tool results recorded ``latency_ms=0`` while ``phase.tool.call.end`` on the
same invocations carried 14ms to 2969ms, which made tool cost invisible to
anything reading the durable record.

The stub sleeps longer than the asserted floor, and ``perf_counter`` elapsed
time only grows under CI load, so the comparison has no fast-side flake.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.team.role.team import (
    CacheConfig,
    RetryPolicy,
    ToolPermissionManifest,
)

_SLEEP_S = 0.05
_FLOOR_MS = 50


@dataclass
class _SlowTool:
    name: str = "runCommand"

    async def execute(self, args: dict[str, Any]) -> Observation:  # type: ignore[override]
        await asyncio.sleep(_SLEEP_S)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"output": "ok", "exit_code": 0},
        )

    def is_idempotent(self) -> bool:
        return True


def _capture() -> tuple[list[tuple[str, dict[str, Any]]], Any]:
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


def _tool_result_latency(*, tool: Any) -> int:
    executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=["runCommand"]))
    captured, fake_publish_ep = _capture()

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        asyncio.run(
            executor.execute(
                tool,
                {"command": "sleep"},
                RetryPolicy(),
                CacheConfig(enabled=False),
                invocation_id="inv-latency",
            )
        )

    results = [p for ep, p in captured if ep == "step.tool_result.record"]
    assert len(results) == 1, f"expected one step.tool_result.record, got {results}"
    return int(results[0]["latency_ms"])


def test_successful_invocation_records_real_latency() -> None:
    assert _tool_result_latency(tool=_SlowTool()) >= _FLOOR_MS


def test_latency_matches_the_sleep_the_tool_actually_took() -> None:
    started = time.perf_counter()
    latency_ms = _tool_result_latency(tool=_SlowTool())
    wall_ms = (time.perf_counter() - started) * 1000
    assert latency_ms <= wall_ms, (
        f"reported latency {latency_ms}ms exceeds the {wall_ms:.0f}ms the invocation actually took"
    )
