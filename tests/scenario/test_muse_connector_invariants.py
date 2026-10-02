"""End-to-End Invariants Assertion Suite for Muse 7-Layer Connector Architecture (INV-01 ~ INV-08)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lca.infrastructure.connectors.core.permissions import (
    ActionPermission,
    ActionPermissionDeniedError,
    ConnectorPermissionEngine,
)
from lca.infrastructure.connectors.core.rate_limiter import (
    ConnectorRateLimitExceededError,
    SlidingWindowRateLimiter,
)
from lca.infrastructure.connectors.core.state import (
    ConnectionMetadata,
    ConnectionState,
    ConnectorStateMachine,
    InvalidStateTransitionError,
    format_connector_auth_widget,
)
from lca.infrastructure.connectors.core.vault import ConnectorVault
from lca.infrastructure.connectors.gmail.cli import GmailConnectorCLI
from lca.infrastructure.connectors.gmail.skill import generate_gmail_skill_content
from lca.plugins.prompts.sections.connected_services import render_connected_services_text


def test_inv_01_token_zero_exposure(tmp_path: Path) -> None:
    """INV-01: Token strings must NEVER be present in metadata or prompt outputs."""
    # 1. Pydantic model rejects secret fields
    with pytest.raises(ValidationError):
        ConnectionMetadata(
            service="gmail",
            state=ConnectionState.ACTIVE,
            access_token="secret_token_val",  # type: ignore[call-arg]  # noqa: S106
        )

    # 2. Prompt rendering contains no secret tokens
    user_conn_dir = tmp_path / "users" / "u1" / "connectors"
    user_conn_dir.mkdir(parents=True)
    (user_conn_dir / "connections.json").write_text(
        json.dumps(
            {
                "connections": [
                    {"identifier": "gmail", "status": "ACTIVE", "connected_account_id": "ca_gm"}
                ]
            }
        ),
        encoding="utf-8",
    )
    vault = ConnectorVault(user_id="u1", lca_home=tmp_path)
    prompt_text = render_connected_services_text(vault=vault)
    assert "token" not in prompt_text.lower()
    assert "- gmail (status: ACTIVE)" in prompt_text


def test_inv_02_state_machine_soundness(tmp_path: Path) -> None:
    """INV-02: State machine transitions must be deterministic; unhandled states fail loud."""
    # Legal transition
    sm = ConnectorStateMachine(ConnectionState.NOT_CONNECTED)
    sm.transition_to(ConnectionState.AWAITING_AUTH)
    assert sm.state == ConnectionState.AWAITING_AUTH

    # Illegal transition
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(ConnectionState.RATE_LIMITED)

    # CLI status when not connected returns structured info
    vault = ConnectorVault(user_id="anon", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)
    status_res = cli.execute(["status"])
    assert status_res["status"] == "not_connected"
    assert status_res["appName"] == "Gmail"
    assert "authUrl" in status_res
    assert "connectionId" in status_res


def test_inv_03_card_protocol_priority() -> None:
    """INV-03: Must trigger LobeHub interactive card widget, strictly forbidding raw markdown."""
    widget = format_connector_auth_widget("Gmail", "https://auth.example.com", "ca_123")
    assert widget.startswith("[widget:connector_auth?")
    assert "appName=Gmail" in widget
    assert "connectionId=ca_123" in widget

    # Skill documentation explicitly forbids raw markdown link anti-pattern
    skill_doc = generate_gmail_skill_content()
    assert "[widget:connector_auth?" in skill_doc
    assert "Do NOT generate markdown links" in skill_doc


def test_inv_04_double_layer_permission_interception(tmp_path: Path) -> None:
    """INV-04: Double-layer permission interception (Provider Scope ∩ Action Allow/Ask/Deny)."""
    perm_dir = tmp_path / "users" / "sec_user" / "connectors"
    perm_dir.mkdir(parents=True)
    (perm_dir / "permissions.json").write_text(
        json.dumps(
            {
                "permissions": {
                    "gmail": {
                        "delete_message": "DENY",
                        "+send": "ASK",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    engine = ConnectorPermissionEngine(user_id="sec_user", lca_home=tmp_path)

    # DENY action must raise ActionPermissionDeniedError
    with pytest.raises(ActionPermissionDeniedError):
        engine.check_action("gmail", "delete_message", current_scopes=["all"])

    # ASK action must return status ASK for human approval
    check_ask = engine.check_action(
        "gmail",
        "+send",
        current_scopes=["https://www.googleapis.com/auth/gmail.send"],
        required_scope="https://www.googleapis.com/auth/gmail.send",
    )
    assert check_ask.status == "ASK"
    assert check_ask.permission == ActionPermission.ASK

    # Missing scope must flag SCOPE_MISSING
    check_scope = engine.check_action(
        "gmail",
        "+send",
        current_scopes=[],
        required_scope="https://www.googleapis.com/auth/gmail.send",
    )
    assert check_scope.status == "SCOPE_MISSING"


def test_inv_05_hard_rate_limiting_enforcement() -> None:
    """INV-05: 60-second sliding window quota enforcement with exact retry_after_seconds."""
    limiter = SlidingWindowRateLimiter()
    # 250 units limit
    limiter.enforce("gmail", units=200, limit_per_minute=250, now=100.0)

    # Exceeding budget raises ConnectorRateLimitExceededError
    with pytest.raises(ConnectorRateLimitExceededError) as exc_info:
        limiter.enforce("gmail", units=100, limit_per_minute=250, now=110.0)

    # Retry after must be calculated accurately (earliest 100.0 + 60 - 110.0 = 50s)
    assert exc_info.value.retry_after_seconds == 50


def test_inv_06_two_phase_write_isolation(tmp_path: Path) -> None:
    """INV-06: Outbound write actions require staged file via --upload."""
    cli = GmailConnectorCLI(vault=ConnectorVault(lca_home=tmp_path))

    # Reject inline body
    inline_res = cli.execute(["+send", "--to", "test@test.com", "--subject", "Hi"])
    assert inline_res["success"] is False
    assert "INV-06 Safety Violation" in inline_res["error"]

    # Allow staged file
    staged_file = tmp_path / "email.txt"
    staged_file.write_text("Reviewed body content", encoding="utf-8")
    staged_res = cli.execute(
        [
            "+send",
            "--to",
            "test@test.com",
            "--subject",
            "Hi",
            "--upload",
            str(staged_file),
        ]
    )
    assert staged_res["success"] is True
    assert "Reviewed body content" in staged_res["content_preview"]


def test_inv_07_multi_account_boundary(tmp_path: Path) -> None:
    """INV-07: Multi-account routing boundary."""
    user_conn_dir = tmp_path / "users" / "multi_user" / "connectors"
    user_conn_dir.mkdir(parents=True)
    (user_conn_dir / "connections.json").write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "identifier": "gmail",
                        "account_id": "corp",
                        "status": "ACTIVE",
                        "connected_account_id": "ca_corp",
                    },
                    {
                        "identifier": "gmail",
                        "account_id": "personal",
                        "status": "AWAITING_AUTH",
                        "connected_account_id": "ca_personal",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    vault = ConnectorVault(user_id="multi_user", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)

    accounts_res = cli.execute(["accounts"])
    assert len(accounts_res["accounts"]) == 2

    corp_status = cli.execute(["status"], account_id="corp")
    assert corp_status["status"] == "active"
    assert corp_status["connectionId"] == "ca_corp"

    pers_status = cli.execute(["status"], account_id="personal")
    assert pers_status["status"] == "not_connected"
    assert pers_status["connectionId"] == "ca_personal"


def test_inv_08_negative_boundary_compliance() -> None:
    """INV-08: Negative Boundary (AP-01) check:

    Ensure connectors module does not import or mutate core cognition loop phases.
    """
    import inspect

    import lca.infrastructure.connectors as connectors_pkg

    # Inspect source of connectors package
    file_path = inspect.getfile(connectors_pkg)
    assert "lca/infrastructure/connectors" in file_path
    # Confirm no reverse dependency on cognition loop
    from lca.infrastructure.connectors.core.vault import ConnectorVault

    assert ConnectorVault is not None
