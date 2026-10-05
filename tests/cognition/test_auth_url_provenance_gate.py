"""Tests for AuthUrlProvenanceGate scoped to authorization URLs (INV-CONN-03)."""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates.auth import (
    AuthUrlProvenanceGate,
    is_auth_intent_url,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.state import AgentState


def _make_state() -> AgentState:
    return AgentState(trace_id="test_trace", task="test_task", budget=Budget())


def test_is_auth_intent_url_detection() -> None:
    """Detects only auth-intent URLs, ignoring regular URLs."""
    # Auth URLs
    assert is_auth_intent_url("https://app.composio.dev/authorize?mode=composio") is True
    assert is_auth_intent_url("https://accounts.google.com/o/oauth2/v2/auth?client_id=123") is True
    assert is_auth_intent_url("https://github.com/login/oauth/authorize") is True
    assert is_auth_intent_url("https://backend.composio.dev/api/v3/auth/redirect?token=abc") is True
    assert is_auth_intent_url("https://slack.com/oauth/v2/authorize") is True

    # Regular non-auth URLs (must NOT be intercepted)
    assert is_auth_intent_url("https://github.com/owner/repo") is False
    assert is_auth_intent_url("https://docs.python.org/3/library/json.html") is False
    assert is_auth_intent_url("https://en.wikipedia.org/wiki/Data_privacy") is False
    assert is_auth_intent_url("http://127.0.0.1:8765/health") is False


@pytest.mark.asyncio
async def test_auth_url_provenance_blocks_hallucinated_auth_link() -> None:
    """INV-CONN-03: Hallucinated auth URL without tool receipt provenance is rewritten."""
    gate = AuthUrlProvenanceGate()
    state = _make_state()

    # Agent hallucinates an auth link without tool receipt
    decision = Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.RESPOND,
        confidence=1.0,
        rationale="告诉用户去授权 Google Drive",
        response_text="请点击下方链接完成授权：[授权链接](https://app.composio.dev/authorize?mode=composio)",
    )

    enforced = await gate.enforce(state, decision)
    # Must be rewritten to remove the hallucinated URL and direct to tool usage
    assert "https://app.composio.dev/authorize?mode=composio" not in (enforced.response_text or "")
    assert "官方" in (enforced.response_text or "") or "工具" in (enforced.response_text or "")


@pytest.mark.asyncio
async def test_auth_url_provenance_allows_legitimate_tool_receipt_url() -> None:
    """INV-CONN-03: Auth URL returned by tool is allowed."""
    gate = AuthUrlProvenanceGate()
    state = _make_state()
    auth_url = "https://backend.composio.dev/api/v3/auth/redirect?token=valid_session_123"

    # Pre-record the URL in state verified provenance
    gate.register_provenance(state, auth_url)

    decision = Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.RESPOND,
        confidence=1.0,
        rationale="返回真实的授权链接",
        response_text=f"请通过官方链接授权：{auth_url}",
    )

    enforced = await gate.enforce(state, decision)
    assert auth_url in (enforced.response_text or "")
    assert enforced.response_text == decision.response_text


@pytest.mark.asyncio
async def test_auth_url_provenance_allows_normal_links_freely() -> None:
    """INV-CONN-03: Non-auth URLs (docs, repos, search results) pass freely without restriction."""
    gate = AuthUrlProvenanceGate()
    state = _make_state()

    normal_text = "文档参考：https://github.com/pallets/click 以及 https://docs.python.org/3/"
    decision = Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.RESPOND,
        confidence=1.0,
        rationale="技术文档引用",
        response_text=normal_text,
    )

    enforced = await gate.enforce(state, decision)
    assert enforced.response_text == normal_text
