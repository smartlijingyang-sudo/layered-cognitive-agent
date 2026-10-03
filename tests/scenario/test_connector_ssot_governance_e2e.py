"""End-to-End Integration Tests for Connector SSOT Governance & Provenance Gate (INV-CONN-01 ~ 06).

Validates the full defense chain:
1. User-scoped SSOT isolation (INV-CONN-01)
2. Fail-closed execution guard with typed exception (INV-CONN-02, INV-CONN-06)
3. Presentation layer adapter formatting widget cards (INV-CONN-02)
4. Auth URL provenance gating (INV-CONN-03)
5. Normal URLs preservation without false-positive killing (INV-CONN-04)
6. Active execution with identity disclosure (INV-CONN-05)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.cognition.brain.decision_gates.auth.url_provenance import (
    AuthUrlProvenanceGate,
    is_auth_intent_url,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.budget import Budget
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.connectors.core.adapter import (
    format_connection_not_active_observation,
)
from lca.infrastructure.connectors.core.exceptions import ConnectionNotActiveError
from lca.infrastructure.connectors.core.guard import ConnectorPreExecutionGuard
from lca.infrastructure.connectors.core.state import ConnectionState
from lca.infrastructure.connectors.core.vault import ConnectorVault


def _make_state() -> AgentState:
    return AgentState(trace_id="test_trace", task="test_task", budget=Budget())


def test_inv_conn_01_user_scoped_isolation(tmp_path: Path) -> None:
    """INV-CONN-01: Each user has strict isolated SSOT connector storage.

    A new user must have zero connections even if other users have active connections.
    """
    lca_home = tmp_path / ".lca"

    # User Alice connects to google-drive
    alice_vault = ConnectorVault(user_id="user_alice", lca_home=lca_home)
    alice_vault.upsert_connection(
        service="google-drive",
        state=ConnectionState.ACTIVE,
        account_identity="alice@company.com",
    )
    assert len(alice_vault.list_active_services()) == 1
    assert "google-drive" in alice_vault.list_active_services()

    # User Bob is brand new - must have zero connections
    bob_vault = ConnectorVault(user_id="user_bob", lca_home=lca_home)
    assert bob_vault.list_active_services() == []
    bob_conn = bob_vault.get_connection("google-drive")
    assert bob_conn is not None
    assert bob_conn.state == ConnectionState.NOT_CONNECTED


def test_inv_conn_02_and_06_execution_guard_fail_closed_and_layering(tmp_path: Path) -> None:
    """INV-CONN-02 & INV-CONN-06: Unauthenticated execution fails closed with typed error.

    The execution guard strictly raises ConnectionNotActiveError (does NOT return markdown/widget).
    The presentation layer adapter formats the typed error into a standard widget observation.
    """
    lca_home = tmp_path / ".lca"
    vault = ConnectorVault(user_id="user_bob", lca_home=lca_home)
    guard = ConnectorPreExecutionGuard(vault=vault)

    # 1. Execution layer: must raise typed error, fail-closed
    with pytest.raises(ConnectionNotActiveError) as exc_info:
        guard.ensure_active("google-drive")

    err = exc_info.value
    assert err.service == "google-drive"
    assert err.user_id == "user_bob"
    assert "NOT_CONNECTED" in str(err) or "not ACTIVE" in str(err)

    # 2. Presentation layer: decoupled adapter converts to widget observation
    obs = format_connection_not_active_observation(err)
    assert obs.success is False
    assert obs.error == "SERVICE_NOT_CONNECTED"
    assert "widget" in obs.payload
    assert obs.payload["widget"].startswith("[widget:connector_auth?")
    assert "appName=Google+Drive" in obs.payload["widget"]


@pytest.mark.asyncio
async def test_inv_conn_03_auth_url_provenance_gate_blocks_hallucination() -> None:
    """INV-CONN-03: Model fabricated auth-intent URLs are strictly intercepted and rewritten."""
    gate = AuthUrlProvenanceGate()
    state = _make_state()

    hallucinated_text = (
        "Here is your Google Drive authorization link: "
        "https://app.composio.dev/authorize?mode=composio&user=alice"
    )

    decision = Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.RESPOND,
        confidence=1.0,
        rationale="尝试输出编造的授权链接",
        response_text=hallucinated_text,
    )

    enforced = await gate.enforce(state, decision)
    assert "https://app.composio.dev/authorize" not in (enforced.response_text or "")
    assert "官方" in (enforced.response_text or "") or "工具" in (enforced.response_text or "")


@pytest.mark.asyncio
async def test_inv_conn_04_normal_urls_pass_without_false_positives() -> None:
    """INV-CONN-04: Documentation, code repositories, and user-provided normal links pass safely."""
    gate = AuthUrlProvenanceGate()
    state = _make_state()

    doc_text = (
        "Check the documentation at https://docs.python.org/3/library/json.html "
        "and the GitHub repo at https://github.com/astral-sh/ruff for details."
    )

    decision = Decision(
        decision_id=new_id("dec"),
        action_type=ActionType.RESPOND,
        confidence=1.0,
        rationale="文档与技术引用",
        response_text=doc_text,
    )

    enforced = await gate.enforce(state, decision)
    assert enforced.response_text == doc_text
    assert not is_auth_intent_url("https://docs.python.org/3/library/json.html")
    assert not is_auth_intent_url("https://github.com/astral-sh/ruff")


def test_inv_conn_05_active_execution_with_identity_transparency(tmp_path: Path) -> None:
    """INV-CONN-05: When connector is ACTIVE, execution guard passes and identity is disclosed."""
    lca_home = tmp_path / ".lca"
    vault = ConnectorVault(user_id="user_alice", lca_home=lca_home)
    vault.upsert_connection(
        service="google-drive",
        state=ConnectionState.ACTIVE,
        account_identity="alice@company.com",
    )

    guard = ConnectorPreExecutionGuard(vault=vault)

    # Must pass without error
    guard.ensure_active("google-drive")

    # Metadata must reveal the explicit identity
    conn = vault.get_connection("google-drive")
    assert conn is not None
    assert conn.is_active is True
    assert conn.account_identity == "alice@company.com"
