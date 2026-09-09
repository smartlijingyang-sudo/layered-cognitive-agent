"""``KernelServeSpawner._probe_lan`` must fail-fast on LAN unreachable.

History: kernel ``--host 127.0.0.1`` + Next.js proxy targeting LAN
(``LCA_GATEWAY_PUBLIC_URL=http://10.36.6.252:8765``) silently looked healthy
on loopback but every /lca-api/* call from the SPA returned 500
(ECONNREFUSED). The post-spawn LAN probe is the regression guard.

ADR-0213 §决定 5 inlines this into ``KernelServeSpawner._step_http_ready``;
the public ``KernelServeService._probe_proxy_lan`` method is removed.
Tests now target the module-level ``_probe_lan`` function so the regression
guard is preserved.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.services.kernel.spawner import (
    KernelServeSpawner,
    _probe_lan,
)


@pytest.fixture
def svc() -> KernelServeSpawner:
    cfg = KernelServeConfig(host="0.0.0.0", port=8765, profile="profiles/web-standard.yaml")  # noqa: S104 — bind-all intentional, see KernelServeConfig
    return KernelServeSpawner(cfg, Path("."))


@pytest.fixture
def env_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LCA_GATEWAY_PUBLIC_URL", raising=False)
    monkeypatch.delenv("OPENAI_PROXY_URL", raising=False)


def test_probe_returns_true_when_no_proxy_env(env_clean: None, svc: KernelServeSpawner) -> None:
    """No proxy env set → assume loopback-only is intentional → True."""
    ok, _reason = _probe_lan(svc._config.host, svc._config.port, svc.health_url)
    assert ok is True


def test_probe_returns_true_when_lan_reachable(svc: KernelServeSpawner) -> None:
    """Proxy env set + LAN /health answers 200 → True."""
    with (
        patch.dict(os.environ, {"LCA_GATEWAY_PUBLIC_URL": "http://10.36.6.252:8765"}, clear=False),
        patch("lca.infrastructure.cli.services.kernel.spawner._http_get", return_value=(200, "")),
    ):
        ok, _ = _probe_lan(svc._config.host, svc._config.port, svc.health_url)
        assert ok is True


def test_probe_returns_false_when_lan_unreachable(svc: KernelServeSpawner) -> None:
    """Proxy env set + LAN /health unreachable → False (regression guard)."""
    with (
        patch.dict(os.environ, {"LCA_GATEWAY_PUBLIC_URL": "http://10.36.6.252:8765"}, clear=False),
        patch("lca.infrastructure.cli.services.kernel.spawner._http_get", return_value=(-1, "")),
    ):
        ok, reason = _probe_lan(svc._config.host, svc._config.port, svc.health_url)
        assert ok is False
        assert reason and reason.startswith("lan_unreachable")


def test_probe_skipped_when_url_parses_to_loopback(svc: KernelServeSpawner) -> None:
    """If LCA_GATEWAY_PUBLIC_URL == loopback health URL, no extra probe needed."""
    loopback_url = svc.health_url  # http://127.0.0.1:8765/health
    with (
        patch.dict(os.environ, {"LCA_GATEWAY_PUBLIC_URL": loopback_url}, clear=False),
        patch("lca.infrastructure.cli.services.kernel.spawner._http_get") as mocked,
    ):
        ok, _ = _probe_lan(svc._config.host, svc._config.port, svc.health_url)
        assert ok is True
        mocked.assert_not_called()


def test_probe_falls_back_to_openai_proxy_url(svc: KernelServeSpawner) -> None:
    """OPENAI_PROXY_URL is the legacy env var lobehub-ui also reads."""
    with (
        patch.dict(os.environ, {"OPENAI_PROXY_URL": "http://10.36.6.252:8765/v1"}, clear=False),
        patch("lca.infrastructure.cli.services.kernel.spawner._http_get", return_value=(200, "")),
    ):
        ok, _ = _probe_lan(svc._config.host, svc._config.port, svc.health_url)
        assert ok is True


def test_probe_skipped_when_host_is_loopback(env_clean: None) -> None:
    """Host is loopback → no LAN probe needed regardless of env."""
    cfg = KernelServeConfig(host="127.0.0.1", port=8765, profile="profiles/web-standard.yaml")
    svc_local = KernelServeSpawner(cfg, Path("."))
    ok, _ = _probe_lan(svc_local._config.host, svc_local._config.port, svc_local.health_url)
    assert ok is True
