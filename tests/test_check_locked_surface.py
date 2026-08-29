"""Tests for scripts/check_locked_surface.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from scripts import check_locked_surface as guard

if TYPE_CHECKING:
    import pytest

_ROOT = Path(__file__).resolve().parent.parent
_ADR = _ROOT / "docs/adr/0103-locked-surface-and-port-policy.md"


# ----- Library-level tests (drive the real check() function) -----


def test_parses_hard_lock_from_adr() -> None:
    hard = guard._hard_paths(_ADR)
    assert "deploy/lobehub" in hard
    assert "lobehub-ui" in hard


def test_parses_soft_lock_from_adr() -> None:
    soft = guard._soft_paths(_ADR)
    assert "gateway/runs/api.py" in soft
    assert "gateway/runs/execute.py" in soft
    assert "gateway/runs/openai_shim.py" in soft


def test_clean_head_exits_zero() -> None:
    rc, violations, _warnings = guard.check(base="HEAD")
    assert rc == 0
    assert violations == []


def test_hard_lock_diff_fails() -> None:
    rc, violations, _warnings = guard.check(
        base="HEAD",
        fake_diff=["deploy/lobehub/patches/runtime/LcaRunDriver.ts"],
    )
    assert rc == 1
    assert any("deploy/lobehub" in v for v in violations)


def test_soft_lock_diff_warns() -> None:
    rc, _violations, warnings = guard.check(base="HEAD", fake_diff=["gateway/runs/api.py"])
    assert rc == 0  # soft-lock alone does not fail
    assert warnings, "soft-lock diff must emit a warning"
    assert any("wire-shape preserved" in w for w in warnings)


def test_soft_lock_with_phrased_commit_message_no_warn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If HEAD's commit body already contains the needle, no warning.
    monkeypatch.setattr(
        guard, "_head_message", lambda: "fix(gateway): wire-shape preserved by adapter"
    )
    _rc, _v, warnings = guard.check(base="HEAD", fake_diff=["gateway/runs/api.py"])
    assert not warnings


# ----- CLI smoke tests -----


def _cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(_ROOT / "scripts/check_locked_surface.py"), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )


def test_cli_self_test_exits_zero() -> None:
    proc = _cli(["--self-test"])
    assert proc.returncode == 0, proc.stderr
    assert "self-test OK" in proc.stdout


def test_cli_hard_lock_via_fake_diff_exits_nonzero() -> None:
    proc = _cli(["--fake-diff", "deploy/lobehub/patches/runtime/LcaRunDriver.ts"])
    assert proc.returncode != 0
    assert "HARD-LOCK" in proc.stderr
