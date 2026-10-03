"""Guard: lobehub dev subprocess env carries LCA P1 wire surface vars.

PR-3 (commit 975416f0) shipped `lcaConnectToGateway` against
`/v1/runs/{run_id}/ws`, but the front-end SPA bundle never received
`NEXT_PUBLIC_LCA_GATEWAY_URL` because vite's DefinePlugin reads
process.env.NEXT_PUBLIC_* once at dev-server start and
`scripts/lca-ops lobehub start/restart` was not threading the value
into the bun subprocess env. The result: chat hit a hard fail with
"[LCA] chat attempted without LCA gateway configured".

The fix lives in `LobeHubService._child_env()` (lca/infrastructure/cli/
services/lobehub/lobehub.py). This test pins the contract so the
guard cannot silently regress.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.cli.config.config import OpsConfig


@pytest.fixture
def lobehub_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Build a LobeHubService without touching the host env."""
    from lca.infrastructure.cli.services.lobehub.lobehub import LobeHubService

    cfg_path = tmp_path / "lca-ops.yaml"
    cfg_path.write_text(
        "kernel_serve:\n  host: 10.36.6.252\n  port: 8765\n  health_path: /health\n"
        "  profile: profiles/web-standard.yaml\n"
        "lobehub:\n  host: 10.36.6.252\n  release: v2.2.13\n  dir: lobehub-ui\n"
        "  dev_port: 3010\n  spa_port: 9876\n  env_template: deploy/lobehub/.env.lca\n"
    )
    cfg = OpsConfig.load(cfg_path)
    monkeypatch.setattr("os.environ", {}, raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return LobeHubService(
        config=cfg.lobehub,
        gateway=cfg.kernel_serve,
        state_dir=state_dir,
        root=tmp_path,
    )


def test_child_env_injects_next_public_lca_gateway_url(
    lobehub_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEXT_PUBLIC_LCA_GATEWAY_URL must be in the dev subprocess env.

    vite's DefinePlugin reads process.env.NEXT_PUBLIC_* at start; if
    it isn't there, the SPA bundle sees `undefined` and chat falls into
    the hard fail branch.
    """
    env = lobehub_service._child_env()
    assert "NEXT_PUBLIC_LCA_GATEWAY_URL" in env, (
        "NEXT_PUBLIC_LCA_GATEWAY_URL missing from lobehub dev subprocess env — "
        "vite DefinePlugin will see undefined and chat will throw '[LCA] chat "
        "attempted without LCA gateway configured'. See "
        "tests/architecture/test_lca_wire_parity.py for the wire SSOT."
    )
    # Must be ws:// (or wss://) — LcaAgentStreamClient builds the
    # WS URL by appending `/v1/runs/{run_id}/ws` to this base.
    url = env["NEXT_PUBLIC_LCA_GATEWAY_URL"]
    assert url.startswith(("ws://", "wss://")), (
        f"NEXT_PUBLIC_LCA_GATEWAY_URL must be ws(s)://, got {url!r}"
    )


def test_child_env_injects_next_public_lca_host_console_default(
    lobehub_service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEXT_PUBLIC_LCA_HOST_CONSOLE defaults to '0' (production-off).

    LcaHostConsole is a dev-only floating terminal that polls
    `/lca-api/api/device/devices` every 30s; it must never mount in a
    production-shaped deployment unless explicitly opted in.
    """
    env = lobehub_service._child_env()
    assert env.get("NEXT_PUBLIC_LCA_HOST_CONSOLE") == "0", (
        "NEXT_PUBLIC_LCA_HOST_CONSOLE must default to '0' — production "
        "deployments must not auto-mount the floating terminal."
    )


def test_child_env_host_console_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Operators can opt-in to host console via env override."""
    from lca.infrastructure.cli.services.lobehub.lobehub import LobeHubService

    cfg_path = tmp_path / "lca-ops.yaml"
    cfg_path.write_text(
        "kernel_serve:\n  host: 10.36.6.252\n  port: 8765\n  health_path: /health\n"
        "  profile: profiles/web-standard.yaml\n"
        "lobehub:\n  host: 10.36.6.252\n  release: v2.2.13\n  dir: lobehub-ui\n"
        "  dev_port: 3010\n  spa_port: 9876\n  env_template: deploy/lobehub/.env.lca\n"
    )
    cfg = OpsConfig.load(cfg_path)
    monkeypatch.setattr("os.environ", {"NEXT_PUBLIC_LCA_HOST_CONSOLE": "1"})
    state_dir = tmp_path / "state_b"
    state_dir.mkdir()
    svc = LobeHubService(
        config=cfg.lobehub,
        gateway=cfg.kernel_serve,
        state_dir=state_dir,
        root=tmp_path,
    )
    env = svc._child_env()
    assert env["NEXT_PUBLIC_LCA_HOST_CONSOLE"] == "1"


def test_child_env_gateway_url_handles_loopback_bind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Kernel serve bind 0.0.0.0 must translate to a browser-reachable URL.

    Vite runs in the same shell as bun; `0.0.0.0` is not browser-reachable
    (browsers interpret it as "this host"). The helper must substitute a
    loopback address so the SPA bundle gets a usable URL.
    """
    from lca.infrastructure.cli.services.lobehub.lobehub import LobeHubService

    cfg_path = tmp_path / "lca-ops.yaml"
    cfg_path.write_text(
        "kernel_serve:\n  host: 0.0.0.0\n  port: 8765\n  health_path: /health\n"
        "  profile: profiles/web-standard.yaml\n"
        "lobehub:\n  host: 10.36.6.252\n  release: v2.2.13\n  dir: lobehub-ui\n"
        "  dev_port: 3010\n  spa_port: 9876\n  env_template: deploy/lobehub/.env.lca\n"
    )
    cfg = OpsConfig.load(cfg_path)
    monkeypatch.setattr("os.environ", {}, raising=False)
    state_dir = tmp_path / "state_c"
    state_dir.mkdir()
    svc = LobeHubService(
        config=cfg.lobehub,
        gateway=cfg.kernel_serve,
        state_dir=state_dir,
        root=tmp_path,
    )
    env = svc._child_env()
    url = env["NEXT_PUBLIC_LCA_GATEWAY_URL"]
    assert "0.0.0.0" not in url, (  # noqa: S104 — checking string, not binding
        f"NEXT_PUBLIC_LCA_GATEWAY_URL must not carry 0.0.0.0; got {url!r}"
    )
    assert url.startswith("ws://")


def test_child_env_injects_memory_guards(lobehub_service) -> None:
    """Child env must set RAYON_NUM_THREADS and NODE_OPTIONS to guard against OOM.

    Vite 8 uses Rolldown (Rust) which by default uses all host CPU cores for parallel
    dependency pre-bundling. On memory-constrained hosts without swap, this causes
    fatal OOM kills unless capped.
    """
    env = lobehub_service._child_env()
    assert env.get("RAYON_NUM_THREADS") == "2"
    assert "--max-old-space-size" in env.get("NODE_OPTIONS", "")


def test_ensure_env_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_ensure_env must not touch .env when values already match, preventing Vite watcher restart loops."""
    from lca.infrastructure.cli.services.lobehub.lobehub import LobeHubService

    cfg_path = tmp_path / "lca-ops.yaml"
    cfg_path.write_text(
        "kernel_serve:\n  host: 10.36.6.252\n  port: 8765\n  health_path: /health\n"
        "  profile: profiles/web-standard.yaml\n"
        "lobehub:\n  host: 10.36.6.252\n  release: v2.2.13\n  dir: lobehub-ui\n"
        "  dev_port: 3010\n  spa_port: 9876\n  env_template: deploy/lobehub/.env.lca\n"
    )
    cfg = OpsConfig.load(cfg_path)
    monkeypatch.setattr("os.environ", {}, raising=False)
    ui_dir = tmp_path / "lobehub-ui"
    ui_dir.mkdir(parents=True)
    template_dir = tmp_path / "deploy" / "lobehub"
    template_dir.mkdir(parents=True)
    template_file = template_dir / ".env.lca"
    template_file.write_text(
        "OPENAI_PROXY_URL=http://replace-me\n"
        "NEXT_PUBLIC_OPENAI_PROXY_URL=http://replace-me\n"
        "OPENAI_API_KEY=replace-me\n"
        "QWEN_PROXY_URL=http://replace-me\n"
        "QWEN_API_KEY=replace-me\n"
        "NEXT_PUBLIC_LCA_GATEWAY_URL=ws://replace-me\n"
        "LCA_GATEWAY_PUBLIC_URL=http://replace-me\n"
        "CUSTOM_KEY=keep_me\n"
    )

    state_dir = tmp_path / "state_d"
    state_dir.mkdir()
    svc = LobeHubService(
        config=cfg.lobehub,
        gateway=cfg.kernel_serve,
        state_dir=state_dir,
        root=tmp_path,
    )

    # First call: .env does not exist, copies and updates -> True
    first_changed = svc._ensure_env()
    assert first_changed is True
    env_content = (ui_dir / ".env").read_text()
    assert "OPENAI_API_KEY=lca-local" in env_content
    assert "CUSTOM_KEY=keep_me" in env_content

    # Second call: .env already has expected values -> False (must not touch file)
    mtime_before = (ui_dir / ".env").stat().st_mtime_ns
    second_changed = svc._ensure_env()
    assert second_changed is False
    mtime_after = (ui_dir / ".env").stat().st_mtime_ns
    assert mtime_before == mtime_after
