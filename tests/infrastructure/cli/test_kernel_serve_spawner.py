"""``KernelServeSpawner`` — slim one-shot Popen wrapper.

After the supervisor refactor, :class:`SpawnResult` carries only 5
fields (``ok`` / ``pid`` / ``port`` / ``exit_code`` / ``duration_ms``).
The spawner does NOT parse stderr, NOT thread-tee logs, NOT match
exit codes to hint commands — all of that lives in the supervisor
or in the kernel-side diagnostic hints.

These tests pin the wire-stable contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.services.kernel.spawner import (
    KernelServeSpawner,
    SpawnResult,
)


@pytest.fixture
def cfg() -> KernelServeConfig:
    return KernelServeConfig(
        host="127.0.0.1",
        port=8765,
        profile="profiles/web-standard.yaml",
    )


@pytest.fixture
def spawner(cfg: KernelServeConfig) -> KernelServeSpawner:
    return KernelServeSpawner(cfg, Path("."))


# ── SpawnResult dataclass contract ──────────────────────────────────


def test_spawn_result_is_frozen_and_extra_forbid() -> None:
    """Wire contract: frozen + extra=forbid; the agent-facing fields
    (ok / pid / exit_code / duration_ms) are first-class citizens.
    """
    r = SpawnResult(ok=True, port=8765)
    assert r.ok is True
    with pytest.raises(ValidationError):
        SpawnResult(ok=True, port=8765, made_up_field=42)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        r.ok = False  # type: ignore[misc]


def test_spawn_result_serializes_with_all_fields() -> None:
    r = SpawnResult(
        ok=False, pid=1234, port=8765, exit_code=1, duration_ms=30135,
    )
    parsed = json.loads(r.model_dump_json())
    assert parsed["ok"] is False
    assert parsed["pid"] == 1234
    assert parsed["exit_code"] == 1
    assert parsed["port"] == 8765
    assert parsed["duration_ms"] == 30135


def test_spawn_result_minimal_success_shape() -> None:
    """Success result: ok=True, pid, port, duration_ms only."""
    r = SpawnResult(ok=True, pid=42, port=8765, duration_ms=120)
    assert r.exit_code is None


# ── spawner construction ─────────────────────────────────────────────


def test_spawner_rejects_legacy_timeout_kwarg() -> None:
    """``port_bound_timeout`` / ``http_timeout`` no longer exist; the
    refactor collapsed to a single ``health_timeout``.
    """
    with pytest.raises(TypeError):
        KernelServeSpawner.__init__(  # type: ignore[call-arg]
            KernelServeConfig(host="127.0.0.1", port=8765, profile="x"),
            Path("."),
            port_bound_timeout=5.0,
            http_timeout=30.0,
        )


# ── run() failure branches ──────────────────────────────────────────


def test_run_returns_failure_on_popen_oserror(spawner: KernelServeSpawner) -> None:
    """OSError from Popen → ``ok=False`` with no exit_code (never started)."""
    with patch(
        "lca.infrastructure.cli.services.kernel.spawner.subprocess.Popen",
        side_effect=OSError(2, "No such file"),
    ):
        result = spawner.run()
    assert result.ok is False
    assert result.pid is None
    assert result.exit_code is None
    assert result.duration_ms >= 0


def test_run_returns_failure_when_subprocess_exits_early(
    spawner: KernelServeSpawner,
) -> None:
    """Subprocess exits before /health answers → ok=False, exit_code set."""
    fake_proc = patch(
        "lca.infrastructure.cli.services.kernel.spawner.subprocess.Popen"
    )
    with fake_proc as mock:
        mock_proc = mock.return_value
        mock_proc.pid = 99999
        mock_proc.poll.return_value = 1  # exits immediately
        mock_proc.wait.return_value = 1
        # probe_health never gets called since poll() != None on first iter
        result = spawner.run()
    assert result.ok is False
    assert result.exit_code == 1