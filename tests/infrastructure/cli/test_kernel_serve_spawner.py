"""``KernelServeSpawner`` — 5 atomic steps + structured SpawnResult.

Replaces the boolean-returning ``KernelServeService._spawn()``. Each
test isolates one step or one timeout / stderr-pruning contract.
End-to-end coverage lives in
``tests/infrastructure/cli/test_kernel_serve_e2e.py`` (or in the integration
suite) — these tests stay subprocess-free so they are deterministic in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.services.kernel.spawner import (
    KernelServeSpawner,
    SpawnResult,
    StepResult,
    _http_get,
    _plugin_ready,
    _prune_old_stderr,
    _stderr_path_for,
)


@pytest.fixture
def spawner() -> KernelServeSpawner:
    cfg = KernelServeConfig(
        host="127.0.0.1",
        port=8765,
        profile="profiles/web-standard.yaml",
    )
    return KernelServeSpawner(cfg, Path("."))


# ── step 1: preflight ──────────────────────────────────────────────


def test_step_preflight_passes_when_profile_has_no_jwt(
    tmp_path: Path, spawner: KernelServeSpawner
) -> None:
    """No JWT plugin in profile → ok, no actionable message."""
    profile = tmp_path / "p.yaml"
    profile.write_text("plugins: []\nbundles: []\n")
    with patch.object(spawner, "_config") as cfg:
        cfg.profile = str(profile)
        cfg.host = "127.0.0.1"
        cfg.port = 8765
        ok, msg, result = spawner._step_preflight()
    assert ok is True
    assert msg is None
    assert result.stage == "preflight"
    assert result.ok is True


def test_step_preflight_blocks_when_env_var_missing(tmp_path: Path) -> None:
    """Profile declares `jwt.private_pem.from_env` but env var unset → block."""
    profile = tmp_path / "p.yaml"
    profile.write_text(
        "plugins:\n"
        "  - id: lca-webserver-jwt-keys\n"
        "    config:\n"
        "      private_pem:\n"
        "        from_env: NONEXISTENT_JWT_SECRET_XYZ\n"
    )
    cfg = KernelServeConfig(host="127.0.0.1", port=8765, profile=str(profile))
    sp = KernelServeSpawner(cfg, Path("."))
    with patch.dict("os.environ", {}, clear=False):
        # Remove env var if it happens to exist.
        import os

        os.environ.pop("NONEXISTENT_JWT_SECRET_XYZ", None)
        ok, msg, result = sp._step_preflight()
    assert ok is False
    assert result.error == "jwt_preflight_blocked"
    assert msg and "NONEXISTENT_JWT_SECRET_XYZ" in msg


# ── step 2: start ────────────────────────────────────────────────────


def test_step_start_records_popen_failure(spawner: KernelServeSpawner) -> None:
    """OSError from Popen → ok=False, error=popen_oserror, stderr_path set."""
    boom = OSError(2, "No such file")
    with patch(
        "lca.infrastructure.cli.services.kernel.spawner.subprocess.Popen",
        side_effect=boom,
    ):
        pid, stderr_path, result = spawner._step_start()
    assert pid is None
    assert stderr_path is not None
    assert result.ok is False
    assert result.error == "popen_oserror"
    assert result.detail.get("errno") == 2


def test_stderr_path_format() -> None:
    """Per-spawn stderr file name encodes pid + UTC timestamp."""
    p = _stderr_path_for(12345)
    assert p.name.startswith("lca-kernel.stderr.12345.")
    assert p.name.endswith(".log")


def test_prune_old_stderr_keeps_n_most_recent(tmp_path: Path) -> None:
    """Older stderr files beyond ``_STDERR_KEEP_N`` are removed."""
    import os
    import time as _time

    saved_dir = tmp_path
    files = []
    # create 7 stale files with monotonic mtime
    for i in range(7):
        f = saved_dir / f"lca-kernel.stderr.1.{i}.log"
        f.write_text("x")
        # touch with increasing mtime
        _time.sleep(0.02)
        os.utime(f, (i + 1, i + 1))
        files.append(f)
    with patch("lca.infrastructure.cli.services.kernel.spawner._STDERR_DIR", saved_dir):
        _prune_old_stderr()
    remaining = sorted(saved_dir.glob("lca-kernel.stderr.*.log"))
    # 5 most recent (by mtime) survive; 2 oldest gone
    assert len(remaining) == 5
    survivors = {p.name for p in remaining}
    # most recent were the LAST two created → index 5 and 6
    assert "lca-kernel.stderr.1.5.log" in survivors
    assert "lca-kernel.stderr.1.6.log" in survivors


# ── step 3: port_bound ──────────────────────────────────────────────


def test_step_port_bound_succeeds_when_port_open(spawner: KernelServeSpawner) -> None:
    """Port reachable within timeout → ok."""
    import os
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(0)
    port = s.getsockname()[1]
    try:
        sp = KernelServeSpawner(
            KernelServeConfig(host="127.0.0.1", port=port, profile="x.yaml"),
            Path("."),
        )
        # pid must be a real PID — use this pytest process's own pid so
        # ``pid_alive`` returns True while we test the port check itself.
        result = sp._step_port_bound(pid=os.getpid(), port=port)
    finally:
        s.close()
    assert result.ok is True
    assert result.detail["port"] == port


def test_step_port_bound_fails_when_kernel_dies(spawner: KernelServeSpawner) -> None:
    """Process dies before port binds → ok=False, error=kernel_died."""
    result = spawner._step_port_bound(pid=999_999_999, port=1)  # port=1 unlikely bound
    assert result.ok is False
    # Either "kernel_died" (PID 999_999_999 doesn't exist) or "port_not_bound"
    assert result.error in {"kernel_died", "port_not_bound"}


# ── step 4: http_ready + plugin_ready ───────────────────────────────


def test_step_http_ready_succeeds_with_status_ok_body(spawner: KernelServeSpawner) -> None:
    """Body `status=ok` → http_ready ok; plugin step then runs."""
    body = json.dumps(
        {
            "status": "ok",
            "plugin": {
                "registered": 6,
                "expected": 6,
                "missing": [],
                "registry_populated": True,
                "pipeline_registered": True,
                "cognitive_driver_registered": True,
            },
        }
    )
    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.read = lambda: body.encode()
    fake_response.__enter__ = lambda self: self
    fake_response.__exit__ = lambda self, *a: None
    with (
        patch(
            "lca.infrastructure.cli.services.kernel.spawner.urllib.request.urlopen",
            return_value=fake_response,
        ),
        patch(
            "lca.infrastructure.cli.services.kernel.spawner._probe_lan", return_value=(True, None)
        ),
    ):
        result = spawner._step_http_ready()
    assert result.ok is True
    assert result.detail["last_status"] == 200


def test_step_http_ready_fails_on_5xx(spawner: KernelServeSpawner) -> None:
    """5xx → http_ready ok=False with `health_status_5xx`."""
    fake_response = MagicMock()
    fake_response.status = 500
    fake_response.read = lambda: b""
    fake_response.__enter__ = lambda self: self
    fake_response.__exit__ = lambda self, *a: None
    with patch(
        "lca.infrastructure.cli.services.kernel.spawner.urllib.request.urlopen",
        return_value=fake_response,
    ):
        # short timeout for the test
        sp = KernelServeSpawner(spawner._config, Path("."), http_timeout=1.0)
        result = sp._step_http_ready()
    assert result.ok is False
    assert result.error == "health_status_500"


def test_step_http_ready_fails_when_status_field_missing(spawner: KernelServeSpawner) -> None:
    """HTTP 200 but body `status != "ok"` → http_ready fails (not 5xx)."""
    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.read = lambda: b'{"other": "value"}'
    fake_response.__enter__ = lambda self: self
    fake_response.__exit__ = lambda self, *a: None
    with patch(
        "lca.infrastructure.cli.services.kernel.spawner.urllib.request.urlopen",
        return_value=fake_response,
    ):
        sp = KernelServeSpawner(spawner._config, Path("."), http_timeout=1.0)
        result = sp._step_http_ready()
    assert result.ok is False
    assert result.error == "health_status_not_ok"


def test_step_http_ready_blocks_lan_when_unreachable(spawner: KernelServeSpawner) -> None:
    """Bind-all host + LAN probe fails → http_ready fails with lan_unreachable."""
    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.read = lambda: b'{"status": "ok"}'
    fake_response.__enter__ = lambda self: self
    fake_response.__exit__ = lambda self, *a: None
    cfg = KernelServeConfig(
        host="0.0.0.0",  # noqa: S104 — bind-all intentional
        port=8765,
        profile="profiles/web-standard.yaml",
    )
    sp = KernelServeSpawner(cfg, Path("."), http_timeout=1.0)
    with (
        patch(
            "lca.infrastructure.cli.services.kernel.spawner.urllib.request.urlopen",
            return_value=fake_response,
        ),
        patch(
            "lca.infrastructure.cli.services.kernel.spawner._probe_lan",
            return_value=(False, "lan_unreachable:http://10.36.6.252:8765/health"),
        ),
    ):
        result = sp._step_http_ready()
    assert result.ok is False
    assert result.error and result.error.startswith("lan_unreachable")


# ── step 5: plugin_ready ───────────────────────────────────────────


def test_step_plugin_ready_passes_when_full(spawner: KernelServeSpawner) -> None:
    body = json.dumps(
        {
            "plugin": {
                "registered": 6,
                "expected": 6,
                "missing": [],
                "registry_populated": True,
                "pipeline_registered": True,
                "cognitive_driver_registered": True,
            }
        }
    )
    result = spawner._step_plugin_ready(body)
    assert result.ok is True


def test_step_plugin_ready_fails_when_missing(spawner: KernelServeSpawner) -> None:
    body = json.dumps(
        {
            "plugin": {
                "registered": 5,
                "expected": 6,
                "missing": ["x.foo"],
                "registry_populated": True,
                "pipeline_registered": True,
                "cognitive_driver_registered": False,
            }
        }
    )
    result = spawner._step_plugin_ready(body)
    assert result.ok is False
    assert result.detail["missing"] == ["x.foo"]


def test_step_plugin_ready_fails_when_no_plugin_field(spawner: KernelServeSpawner) -> None:
    """Pre-0213 /health body without `plugin` field → fails (boot not ready)."""
    body = json.dumps({"status": "ok"})
    result = spawner._step_plugin_ready(body)
    assert result.ok is False
    assert result.error == "plugin_not_ready"


# ── SpawnResult dataclass ──────────────────────────────────────────


def test_spawn_result_is_frozen_and_extra_forbid() -> None:
    """Wire contract: frozen + extra=forbid."""
    from pydantic import ValidationError

    r = SpawnResult(ok=True, port=8765)
    assert r.ok is True
    with pytest.raises(ValidationError):
        SpawnResult(ok=True, port=8765, made_up_field=42)  # type: ignore[call-arg]
    # pydantic frozen: attribute assignment raises ValidationError (not FrozenInstanceError)
    with pytest.raises(ValidationError):
        r.ok = False  # type: ignore[misc]


def test_spawn_result_serializable_to_json() -> None:
    """agent-readable JSON dump must include actionable + steps + pid."""
    r = SpawnResult(
        ok=False,
        failed_stage="http_ready",
        steps=[
            StepResult(stage="preflight", ok=True, duration_ms=5),
            StepResult(stage="start", ok=True, duration_ms=80, detail={"pid": 1234}),
            StepResult(stage="port_bound", ok=True, duration_ms=50),
            StepResult(stage="http_ready", ok=False, duration_ms=30000, error="health_timeout"),
        ],
        pid=1234,
        port=8765,
        stderr_path=Path("/tmp/x.log"),  # noqa: S108 — test fixture
        duration_ms=30135,
        actionable="kernel pid=1234 bound TCP 8765 but /health did not answer. Inspect stderr: /tmp/x.log",
    )
    s = r.model_dump_json()
    parsed = json.loads(s)
    assert parsed["ok"] is False
    assert parsed["failed_stage"] == "http_ready"
    assert parsed["pid"] == 1234
    assert parsed["actionable"] is not None
    assert parsed["steps"][0]["stage"] == "preflight"


# ── helpers ────────────────────────────────────────────────────────


def test_http_get_returns_minus_one_on_network_error() -> None:
    """_http_get returns (-1, "") on connection failure."""
    with patch(
        "lca.infrastructure.cli.services.kernel.spawner.urllib.request.urlopen",
        side_effect=OSError("refused"),
    ):
        code, body = _http_get("http://127.0.0.1:1/health", timeout=0.5)
    assert code == -1
    assert body == ""


def test_plugin_ready_handles_malformed_body() -> None:
    ok, detail = _plugin_ready("not json")
    assert ok is False
    assert detail["registered"] == 0
