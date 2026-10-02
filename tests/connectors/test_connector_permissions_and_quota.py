"""Tests for Double-Layer Permission Engine & Sliding-Window Rate Limiter (INV-04, INV-05)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.infrastructure.connectors.core.permissions import (
    ActionPermission,
    ActionPermissionDeniedError,
    ConnectorPermissionEngine,
)
from lca.infrastructure.connectors.core.rate_limiter import (
    ConnectorRateLimitExceededError,
    SlidingWindowRateLimiter,
)


def test_permission_engine_allow_ask_deny_inv04(tmp_path: Path) -> None:
    # Set up user permissions file
    perm_dir = tmp_path / "users" / "test_user" / "connectors"
    perm_dir.mkdir(parents=True)
    perm_file = perm_dir / "permissions.json"
    perm_file.write_text(
        json.dumps(
            {
                "permissions": {
                    "gmail": {
                        "+read": "ALLOW",
                        "+send": "ASK",
                        "delete": "DENY",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    engine = ConnectorPermissionEngine(user_id="test_user", lca_home=tmp_path)

    # 1. ALLOW check
    res_read = engine.check_action(
        service="gmail",
        action="+read",
        current_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    assert res_read.status == "ALLOW"

    # 2. ASK check (requires human approval)
    res_send = engine.check_action(
        service="gmail",
        action="+send",
        current_scopes=["https://www.googleapis.com/auth/gmail.send"],
        required_scope="https://www.googleapis.com/auth/gmail.send",
    )
    assert res_send.status == "ASK"
    assert res_send.permission == ActionPermission.ASK

    # 3. DENY check (INV-04: hard failure)
    with pytest.raises(ActionPermissionDeniedError) as exc_info:
        engine.check_action(
            service="gmail",
            action="delete",
            current_scopes=["https://www.googleapis.com/auth/gmail.modify"],
        )
    assert "DENIED" in str(exc_info.value)


def test_permission_engine_missing_scope_triggers_additional_access() -> None:
    engine = ConnectorPermissionEngine()
    res = engine.check_action(
        service="gmail",
        action="+send",
        current_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        required_scope="https://www.googleapis.com/auth/gmail.send",
    )
    assert res.status == "SCOPE_MISSING"
    assert res.missing_scope == "https://www.googleapis.com/auth/gmail.send"


def test_sliding_window_rate_limiter_inv05() -> None:
    limiter = SlidingWindowRateLimiter()
    # 250 units per minute limit
    limit = 250

    # First call: +send 100 units -> OK (consumed 100)
    allowed, retry_after = limiter.check_and_consume(
        "gmail", units=100, limit_per_minute=limit, now=1000.0
    )
    assert allowed is True
    assert retry_after == 0

    # Second call: +send 100 units -> OK (consumed 200)
    allowed, retry_after = limiter.check_and_consume(
        "gmail", units=100, limit_per_minute=limit, now=1010.0
    )
    assert allowed is True
    assert retry_after == 0

    # Third call: +send 100 units (would be 300 > 250) -> INV-05: Blocked with retry_after_seconds
    allowed, retry_after = limiter.check_and_consume(
        "gmail", units=100, limit_per_minute=limit, now=1020.0
    )
    assert allowed is False
    # Earliest record at 1000.0 expires at 1060.0. Current time 1020.0 -> retry_after should be 40s.
    assert retry_after == 40

    # Verify raise helper
    with pytest.raises(ConnectorRateLimitExceededError) as exc_info:
        limiter.enforce("gmail", units=100, limit_per_minute=limit, now=1020.0)
    assert exc_info.value.retry_after_seconds == 40

    # Advance time past the 60s window (now=1061.0) -> First record expired, current usage is 100.
    # Consuming 100 units now -> 200 <= 250 -> OK
    allowed, retry_after = limiter.check_and_consume(
        "gmail", units=100, limit_per_minute=limit, now=1061.0
    )
    assert allowed is True
    assert retry_after == 0
