"""Regression: ``body.sandbox.exit`` must carry the real effect outcome.

Bug: ``SimpleSafeExecutor.execute`` bracketed the world-effect window with
``commit_body_sandbox_enter`` / ``commit_body_sandbox_exit`` but never passed
``outcome``, so the exit fact took the ``"success"`` default on every
invocation. In ``run_5490e7c8a76c`` all 10 ``body.sandbox.exit`` events read
``outcome=success`` while two of those invocations had failed: a ``runCommand``
returning ``cd: /files: No such file or directory`` and an ``executeCode``
raising ``TypeError``. The sandbox boundary therefore asserted the opposite of
the tool result recorded microseconds later on the same invocation_id.

``Outcome`` (``lca/contracts/observability/evidence/outcome.py``) is the
close-set SSOT and already contains ``"failure"``; no new value is introduced.
"""

from __future__ import annotations

import asyncio
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


@dataclass
class _StubTool:
    name: str = "runCommand"
    success: bool = True

    async def execute(self, args: dict[str, Any]) -> Observation:  # type: ignore[override]
        return Observation(
            observation_id=new_id("obs"),
            success=self.success,
            payload={"output": "ok" if self.success else "", "exit_code": 0 if self.success else 1},
            error=None
            if self.success
            else "/bin/sh: line 0: cd: /files: No such file or directory",
        )

    def is_idempotent(self) -> bool:
        return True


def _permission() -> ToolPermissionManifest:
    return ToolPermissionManifest(allowed_tools=["runCommand"])


def _captured_publish_ep() -> tuple[list[tuple[str, dict[str, Any]]], Any]:
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


def _sandbox_exit_outcome(tool: _StubTool) -> str:
    executor = SimpleSafeExecutor(_permission())
    captured, fake_publish_ep = _captured_publish_ep()

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        asyncio.run(
            executor.execute(
                tool,
                {"command": "cd /files"},
                RetryPolicy(),
                CacheConfig(enabled=False),
                invocation_id="inv-sandbox-exit",
            )
        )

    exits = [p for ep, p in captured if ep == "body.sandbox.exit"]
    assert len(exits) == 1, f"expected one body.sandbox.exit, got {exits}"
    return str(exits[0]["outcome"])


def test_failed_tool_records_failed_sandbox_exit() -> None:
    assert _sandbox_exit_outcome(_StubTool(success=False)) == "failure"


def test_successful_tool_records_successful_sandbox_exit() -> None:
    assert _sandbox_exit_outcome(_StubTool(success=True)) == "success"


def test_sandbox_exit_agrees_with_tool_result_on_same_invocation() -> None:
    """Both facts describe one invocation; they must not contradict."""
    executor = SimpleSafeExecutor(_permission())
    captured, fake_publish_ep = _captured_publish_ep()

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        asyncio.run(
            executor.execute(
                _StubTool(success=False),
                {"command": "cd /files"},
                RetryPolicy(),
                CacheConfig(enabled=False),
                invocation_id="inv-agree",
            )
        )

    by_ep = dict(captured)
    exit_ok = by_ep["body.sandbox.exit"]["outcome"] == "success"
    result_ok = by_ep["step.tool_result.record"]["ok"] is True
    assert exit_ok == result_ok, (
        f"body.sandbox.exit says success={exit_ok} but step.tool_result.record "
        f"says ok={result_ok} for the same invocation"
    )
