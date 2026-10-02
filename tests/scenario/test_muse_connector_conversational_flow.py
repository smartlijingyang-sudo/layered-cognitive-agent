"""Strict Process/Flow Integration Tests for Muse 7-Layer Connector Subsystem.

Simulates real multi-step user scenarios:
1. Scenario A: Onboarding & First-time Connection Flow (Unconnected -> Widget -> Connected)
2. Scenario B: Two-Phase Write & Approval Flow (+send -> Safety Gate -> --upload Staging -> Execution)
3. Scenario C: Incremental Scope Elevation Flow (Read-only -> Elevation Card -> Full Permission)
4. Scenario D: Remote Token Revocation & Re-auth Flow (Revoked -> REAUTHORIZATION_REQUIRED -> Re-auth)
5. Scenario E: Sliding Window Rate Limit & Backoff Flow (Quota Exceeded -> Retry-After Backoff -> Self-Heal)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.connectors.core.permissions import (
    ActionPermission,
    ConnectorPermissionEngine,
)
from lca.infrastructure.connectors.core.rate_limiter import (
    ConnectorRateLimitExceededError,
    SlidingWindowRateLimiter,
)
from lca.infrastructure.connectors.core.state import (
    ConnectionState,
    ConnectorStateMachine,
    format_connector_auth_widget,
)
from lca.infrastructure.connectors.core.vault import ConnectorVault, atomic_write_json
from lca.infrastructure.connectors.gmail.cli import GmailConnectorCLI
from lca.plugins.prompts.sections.connected_services import render_connected_services_text


def test_flow_scenario_a_first_time_connection(tmp_path: Path) -> None:
    """Scenario A: Initial unconfigured user asks for Gmail -> Agent gets widget -> Authorizes -> Active."""
    vault = ConnectorVault(user_id="user_alice", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)

    # 1. Step 1: Pre-flight check before connecting
    pre_text = render_connected_services_text(vault=vault)
    assert "No external services are currently connected" in pre_text

    # 2. Step 2: Agent runs `gmail status`
    status_1 = cli.execute(["status"])
    assert status_1["status"] == "not_connected"
    assert status_1["appName"] == "Gmail"
    assert "[widget:connector_auth?" in status_1["widget"]
    assert "mode=initial" in status_1["widget"]

    # 3. Step 3: User finishes OAuth in LobeHub popup -> backend records active connection
    user_conn_file = tmp_path / "users" / "user_alice" / "connectors" / "connections.json"
    atomic_write_json(
        user_conn_file,
        {
            "connections": [
                {
                    "identifier": "gmail",
                    "status": "ACTIVE",
                    "connected_account_id": "ca_alice_gmail",
                    "redirect_url": None,
                }
            ]
        },
    )

    # 4. Step 4: Next turn, agent runs `gmail status` again -> Active!
    status_2 = cli.execute(["status"])
    assert status_2["status"] == "active"
    assert status_2["connectionId"] == "ca_alice_gmail"

    # 5. Step 5: System prompt now reflects active belief without tool call
    post_text = render_connected_services_text(vault=vault)
    assert "- gmail (status: ACTIVE)" in post_text


def test_flow_scenario_b_two_phase_write_and_approval(tmp_path: Path) -> None:
    """Scenario B: User asks to send email -> Permission Gate flags ASK -> Draft staged to file -> Execution."""
    # Setup active connection and permissions
    user_dir = tmp_path / "users" / "user_bob" / "connectors"
    atomic_write_json(
        user_dir / "connections.json",
        {
            "connections": [
                {
                    "identifier": "gmail",
                    "status": "ACTIVE",
                    "connected_account_id": "ca_bob",
                    "scopes": ["https://www.googleapis.com/auth/gmail.send"],
                }
            ]
        },
    )
    atomic_write_json(
        user_dir / "permissions.json",
        {
            "permissions": {
                "gmail": {
                    "+send": "ASK",
                    "+read": "ALLOW",
                }
            }
        },
    )

    vault = ConnectorVault(user_id="user_bob", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)
    perm_engine = ConnectorPermissionEngine(user_id="user_bob", lca_home=tmp_path)

    # 1. Step 1: Permission check before executing write action
    check = perm_engine.check_action(
        service="gmail",
        action="+send",
        current_scopes=["https://www.googleapis.com/auth/gmail.send"],
        required_scope="https://www.googleapis.com/auth/gmail.send",
    )
    assert check.status == "ASK"
    assert check.permission == ActionPermission.ASK

    # 2. Step 2: Attempting to call +send without staged file must be blocked by INV-06
    fail_res = cli.execute(["+send", "--to", "boss@corp.com", "--subject", "Status"])
    assert fail_res["success"] is False
    assert "INV-06 Safety Violation" in fail_res["error"]

    # 3. Step 3: Agent stages draft content to temporary file for human preview
    draft_file = tmp_path / "staging" / "draft_001.eml"
    draft_file.parent.mkdir(parents=True)
    draft_file.write_text("Hello Boss, Project Alpha is shipped.", encoding="utf-8")

    # 4. Step 4: After human approval, execute +send with --upload staged file
    success_res = cli.execute(
        [
            "+send",
            "--to",
            "boss@corp.com",
            "--subject",
            "Status Update",
            "--upload",
            str(draft_file),
        ]
    )
    assert success_res["success"] is True
    assert success_res["to"] == "boss@corp.com"
    assert "Hello Boss" in success_res["content_preview"]


def test_flow_scenario_c_incremental_scope_elevation(tmp_path: Path) -> None:
    """Scenario C: Read-only scope is active -> Write command triggers incremental elevation card."""
    user_dir = tmp_path / "users" / "user_charlie" / "connectors"
    atomic_write_json(
        user_dir / "connections.json",
        {
            "connections": [
                {
                    "identifier": "gmail",
                    "status": "ACTIVE",
                    "connected_account_id": "ca_charlie",
                    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
                }
            ]
        },
    )

    perm_engine = ConnectorPermissionEngine(user_id="user_charlie", lca_home=tmp_path)

    # Check send action against read-only scope
    check = perm_engine.check_action(
        service="gmail",
        action="+send",
        current_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        required_scope="https://www.googleapis.com/auth/gmail.send",
    )
    assert check.status == "SCOPE_MISSING"
    assert check.missing_scope == "https://www.googleapis.com/auth/gmail.send"

    # Agent emits elevation card widget with mode=add_scope
    elevation_widget = format_connector_auth_widget(
        app_name="Gmail",
        auth_url="https://backend.composio.dev/auth/elevate",
        connection_id="ca_charlie",
        mode="add_scope",
        scope="https://www.googleapis.com/auth/gmail.send",
    )
    assert "[widget:connector_auth?" in elevation_widget
    assert "mode=add_scope" in elevation_widget
    assert "scope=" in elevation_widget


def test_flow_scenario_d_token_revocation_halts_infinite_retries(tmp_path: Path) -> None:
    """Scenario D: User revokes token remotely -> State machine transitions to REAUTHORIZATION_REQUIRED -> Halts retry loops."""
    user_dir = tmp_path / "users" / "user_dave" / "connectors"
    # Remote provider revoked token
    atomic_write_json(
        user_dir / "connections.json",
        {
            "connections": [
                {
                    "identifier": "gmail",
                    "status": "REVOKED",
                    "connected_account_id": "ca_dave",
                }
            ]
        },
    )

    vault = ConnectorVault(user_id="user_dave", lca_home=tmp_path)
    conn = vault.get_connection("gmail")
    assert conn is not None
    assert conn.state == ConnectionState.REAUTHORIZATION_REQUIRED

    # State machine must verify that REAUTHORIZATION_REQUIRED can only transition to AWAITING_AUTH, not ACTIVE
    sm = ConnectorStateMachine(initial_state=conn.state)
    assert sm.can_transition_to(ConnectionState.ACTIVE) is False
    assert sm.can_transition_to(ConnectionState.AWAITING_AUTH) is True


def test_flow_scenario_e_rate_limit_backoff_and_self_heal() -> None:
    """Scenario E: Agent issues burst requests -> Limit exceeded -> Backs off -> Succeeds after window slides."""
    limiter = SlidingWindowRateLimiter()
    limit = 250

    # Burst 1: 100 units at t=0s
    ok1, _ = limiter.check_and_consume("gmail", units=100, limit_per_minute=limit, now=0.0)
    assert ok1 is True

    # Burst 2: 100 units at t=10s
    ok2, _ = limiter.check_and_consume("gmail", units=100, limit_per_minute=limit, now=10.0)
    assert ok2 is True

    # Burst 3: 100 units at t=20s (Total = 300 > 250) -> Blocked!
    ok3, retry_after = limiter.check_and_consume(
        "gmail", units=100, limit_per_minute=limit, now=20.0
    )
    assert ok3 is False
    assert retry_after == 40  # (0.0 + 60.0) - 20.0 = 40s

    # Enforcement guard raises typed error
    with pytest.raises(ConnectorRateLimitExceededError) as exc_info:
        limiter.enforce("gmail", units=100, limit_per_minute=limit, now=20.0)
    assert exc_info.value.retry_after_seconds == 40

    # Agent waits 40s (now=61.0s) -> Burst 1 expired, current usage is 100.
    # Retry now succeeds!
    ok4, _ = limiter.check_and_consume("gmail", units=100, limit_per_minute=limit, now=61.0)
    assert ok4 is True
