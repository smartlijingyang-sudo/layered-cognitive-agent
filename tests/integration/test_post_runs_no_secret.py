"""Integration test for the ``POST /lca-api/runs → jwt_secret_unconfigured`` path.

Regression target: the bug fixed in ``fix/runs-jwt-seam`` —
``lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.render_create_run_receipt``
used to let ``mint_user_jwt`` raise :class:`InvalidTokenError` and surface
as a 500. After the fix, missing JWT key material produces a structured
503 with ``code == "jwt_secret_unconfigured"``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    render_create_run_receipt,
)
from lca.plugins.transport.webserver.jwt_keys_seam.jwt_keys import (
    JwtKeys,
    generate_dev_keypair,
)


@pytest.fixture(autouse=True)
def _scrub_jwt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Hermetic "no JWT material" precondition: tests/integration/p1/conftest.py
    # installs LCA_JWT_SECRET process-wide via a session fixture, and
    # mint_user_jwt falls back to it when jwt_keys is None. Without the scrub
    # this module's 503 regression test passes in isolation but fails in
    # directory-batch runs (same pattern as test_ws_handshake_jwt.py).
    monkeypatch.delenv("LCA_JWT_SECRET", raising=False)
    monkeypatch.delenv("LCA_JWT_PUBLIC_KEY", raising=False)


@dataclass(frozen=True, slots=True)
class _RunReceiptStub:
    run_id: str = "run_test_0001"
    trace_id: str = "trace_test_0001"
    accepted: bool = True


@dataclass(frozen=True, slots=True)
class _AgentRefStub:
    agent_id: str = "agt_test"
    name: str = "test-agent"


@dataclass(frozen=True, slots=True)
class _Response:
    """Minimal Starlette ``JSONResponse`` stand-in for assertions."""

    status_code: int
    body: dict[str, object]


def test_render_create_run_receipt_with_jwt_keys_returns_envelope() -> None:
    """Happy path: dev-mode JwtKeys → 202 envelope with ws_token."""
    priv, pub = generate_dev_keypair()
    keys = JwtKeys(private_pem=priv, public_pem=pub)

    response = render_create_run_receipt(
        _RunReceiptStub(),
        _AgentRefStub(),
        jwt_keys=keys,
    )
    body = _Response(status_code=response.status_code, body=_decode(response))
    assert body.status_code == 202
    assert body.body["run_id"] == "run_test_0001"
    assert body.body["trace_id"] == "trace_test_0001"
    assert body.body["ws_token"].count(".") == 2  # header.payload.signature


def test_render_create_run_receipt_without_jwt_keys_returns_503() -> None:
    """Regression: handler must not propagate to 500 when the key is missing."""
    response = render_create_run_receipt(
        _RunReceiptStub(),
        _AgentRefStub(),
        jwt_keys=None,
    )
    body = _Response(status_code=response.status_code, body=_decode(response))
    assert body.status_code == 503
    err = body.body["error"]
    assert err["code"] == "jwt_secret_unconfigured"
    assert "JWT signing key is not configured" in err["message"]


def _decode(response: object) -> dict[str, object]:
    """Pull the JSON body out of a Starlette ``JSONResponse`` without
    touching its private attributes.
    """
    import json

    raw = response.body  # type: ignore[attr-defined]
    return json.loads(bytes(raw).decode("utf-8"))
