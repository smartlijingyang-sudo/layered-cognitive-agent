"""``KernelServeService._probe_proxy_lan`` must fail-fast on LAN unreachable.

History: kernel ``--host 127.0.0.1`` + Next.js proxy targeting LAN
(``LCA_GATEWAY_PUBLIC_URL=http://10.36.6.252:8765``) silently looked healthy
on loopback but every /lca-api/* call from the SPA returned 500
(ECONNREFUSED). The post-spawn LAN probe is the regression guard.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.services.kernel.serve import KernelServeService


@pytest.fixture
def svc() -> KernelServeService:
    cfg = KernelServeConfig(host="0.0.0.0", port=8765, profile="profiles/web-standard.yaml")  # noqa: S104 — bind-all intentional, see KernelServeConfig
    return KernelServeService(cfg, Path("."))


@pytest.fixture
def env_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LCA_GATEWAY_PUBLIC_URL", raising=False)
    monkeypatch.delenv("OPENAI_PROXY_URL", raising=False)


def test_probe_returns_true_when_no_proxy_env(env_clean: None, svc: KernelServeService) -> None:
    """No proxy env set → assume loopback-only is intentional → True."""
    assert svc._probe_proxy_lan() is True


def test_probe_returns_true_when_lan_reachable(svc: KernelServeService) -> None:
    """Proxy env set + LAN /health answers 200 → True."""
    with patch.dict(
        os.environ, {"LCA_GATEWAY_PUBLIC_URL": "http://10.36.6.252:8765"}, clear=False
    ), patch(
        "lca.infrastructure.cli.services.kernel.serve.http_ready", return_value=True
    ):
        assert svc._probe_proxy_lan() is True


def test_probe_returns_false_when_lan_unreachable(svc: KernelServeService) -> None:
    """Proxy env set + LAN /health unreachable → False (regression guard)."""
    with patch.dict(
        os.environ, {"LCA_GATEWAY_PUBLIC_URL": "http://10.36.6.252:8765"}, clear=False
    ), patch(
        "lca.infrastructure.cli.services.kernel.serve.http_ready", return_value=False
    ):
        assert svc._probe_proxy_lan() is False


def test_probe_skipped_when_url_parses_to_loopback(svc: KernelServeService) -> None:
    """If LCA_GATEWAY_PUBLIC_URL == loopback health URL, no extra probe needed."""
    loopback_url = svc.health_url  # http://127.0.0.1:8765/health
    with patch.dict(os.environ, {"LCA_GATEWAY_PUBLIC_URL": loopback_url}, clear=False), patch(
        "lca.infrastructure.cli.services.kernel.serve.http_ready"
    ) as mocked:
        # Should return True without invoking http_ready at all.
        assert svc._probe_proxy_lan() is True
        mocked.assert_not_called()


def test_probe_falls_back_to_openai_proxy_url(svc: KernelServeService) -> None:
    """OPENAI_PROXY_URL is the legacy env var lobehub-ui also reads."""
    with patch.dict(
        os.environ, {"OPENAI_PROXY_URL": "http://10.36.6.252:8765/v1"}, clear=False
    ), patch(
        "lca.infrastructure.cli.services.kernel.serve.http_ready", return_value=True
    ):
        assert svc._probe_proxy_lan() is True
