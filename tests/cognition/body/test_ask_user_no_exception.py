"""Regression: ``askUserQuestion`` must not escape as an exception.

The HITL pause travels the graph path (``Decision.needs_approval`` →
``act.approve.gate`` → ``intervene.interrupt`` → ``WAITING_INPUT``). A direct
tool invoke returns the approval request as data so ``Body`` keeps its
``Observation`` contract; an escaping ``ApprovalPendingError`` is folded by
``concept.effect.execute._dispatch`` into a FAILED ``EffectReceipt`` and the
run dies as FAILED instead of pausing.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor
from lca.contracts.models.team.role.team import (
    CacheConfig,
    RetryPolicy,
    ToolPermissionManifest,
)
from lca.infrastructure.tools.ask_user import AskUserExecutor


def _questions() -> dict[str, Any]:
    return {
        "questions": [
            {
                "question": "Which flight?",
                "header": "Flight",
                "options": [
                    {"label": "CA123", "description": "Air China morning"},
                    {"label": "MU456", "description": "China Eastern noon"},
                ],
            }
        ]
    }


def test_direct_invoke_returns_approval_request_as_data() -> None:
    obs = asyncio.run(AskUserExecutor().askUserQuestion(_questions()))
    assert obs.success is False
    assert obs.error == "waiting for human approval"
    request = obs.extra.get("approval_request")
    assert isinstance(request, dict)
    assert request["type"] == "ask_user_question"
    assert request["questions"][0]["question"] == "Which flight?"


def test_direct_invoke_validation_failure_stays_observation() -> None:
    obs = asyncio.run(AskUserExecutor().askUserQuestion({"questions": []}))
    assert obs.success is False
    assert "non-empty array" in (obs.error or "")


def test_executor_does_not_raise_or_retry_on_ask_user() -> None:
    """Through ``SimpleSafeExecutor``: one attempt, returned Observation, no raise."""
    from lca.infrastructure.tools.ask_user import MANIFEST
    from lca.infrastructure.tools.builder.builder import build_tools_from_manifest

    tools = build_tools_from_manifest(MANIFEST, AskUserExecutor())
    tool = next(t for t in tools if t.name == "askUserQuestion")
    executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=["askUserQuestion"]))
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

    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        obs = asyncio.run(
            executor.execute(
                tool,
                _questions(),
                RetryPolicy(),
                CacheConfig(enabled=False),
                invocation_id="inv-ask-user",
            )
        )
    assert obs.success is False
    assert isinstance(obs.extra.get("approval_request"), dict)
    starts = [p for ep, p in captured if ep == "body.tool.execute.start"]
    assert len(starts) == 1, f"askUserQuestion must attempt exactly once, got {len(starts)}"
