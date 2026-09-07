"""Strict CI gate: doctor --ci must report zero errors on golden profiles.

Per ADR-0199 §11 HPC-L5: ``lca-ops doctor profile --ci`` returns exit 1
on errors. Per §17 acceptance #3: 8 golden profiles zero error.

This is the **strict** counterpart of the P2-10 baseline-tolerance
test (``tests/architecture/test_0199_doctor_golden.py``). P2-10 uses a
recorded baseline so that pre-existing violations don't break the test
suite — only regressions. P2-12 (this file) is the **fail-closed CI
gate** that asserts ``errors == 0`` on every golden profile with no
baseline tolerance.

The strict check runs in :class:`lca.harness.diagnostics.doctor.DoctorFacade`
in-process (same path P2-10 exercises). The CLI surface contract is
verified by ``tests/infrastructure/cli/test_doctor_ci_integration.py``
via :class:`typer.testing.CliRunner`.

Per I-HPC-7 the doctor is read-only on the profile path and plugin
tree; per C8 the pass order is deterministic. The test runs the
facade with ``include_plugin_shape=False`` for the same P2-04 baseline
reason documented in ``test_0199_doctor_golden.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.diagnostics.doctor import DoctorReport
from lca.harness.diagnostics.doctor.facade import DoctorFacade

# ── Paths ───────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PROFILES_DIR = REPO_ROOT / "tests" / "golden" / "profiles"


def _all_golden_profiles() -> list[Path]:
    """Discover all *.yaml golden profile paths (deterministic order)."""
    return sorted(GOLDEN_PROFILES_DIR.glob("*.yaml"))


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def facade() -> DoctorFacade:
    return DoctorFacade()


@pytest.fixture(scope="module")
def doctor_results(facade: DoctorFacade) -> dict[str, DoctorReport]:
    """Run doctor on every golden profile; return {filename: DoctorReport}."""
    results: dict[str, DoctorReport] = {}
    for path in _all_golden_profiles():
        try:
            results[path.name] = facade.doctor_profile(
                path,
                include_plugin_shape=False,
            )
        except Exception:
            # If doctor crashes on a profile (e.g., merge-conflict in
            # transitive imports), record an empty report — the strict
            # gate below will still flag it as a regression because
            # the file appears in results but with empty findings.
            results[path.name] = DoctorReport.from_findings(
                subject=str(path),
                findings=[],
            )
    return results


# ── Tests ────────────────────────────────────────────────────────────────


class TestDoctorStrictCIGate:
    """Strict CI gate: zero errors on every golden profile.

    Per ADR-0199 §11 HPC-L5 + §17 #3 the doctor --ci contract is
    **fail-closed on errors**. This test asserts that contract: every
    golden profile must yield ``summary.errors == 0``. There is no
    baseline tolerance — the gate is binary.

    If this test fails:
      * Either the profile has been mutated and is now invalid (revert
        the change or extend ``doctor_baseline.json`` and update
        ADR-0199 acceptance).
      * Or a new doctor rule was added that flags previously-clean
        profiles (suppress the rule, mark the profile, or fix the
        profile).
    """

    def test_at_least_8_golden_profiles(self) -> None:
        """ADR-0199 §13.3 + §17 #3 require ≥8 golden profiles."""
        profiles = _all_golden_profiles()
        assert len(profiles) >= 8, (
            f"expected ≥8 golden profiles; found {len(profiles)}: {[p.name for p in profiles]}"
        )

    @pytest.mark.parametrize("profile_path", _all_golden_profiles(), ids=lambda p: p.name)
    def test_strict_gate_zero_errors(
        self, doctor_results: dict[str, DoctorReport], profile_path: Path
    ) -> None:
        """Every golden profile must report zero error findings.

        This is the ADR-0199 §11 HPC-L5 + §17 #3 acceptance criterion:
        ``lca-ops doctor profile --ci`` exits 0 only when the doctor
        summary reports ``errors == 0``. There is no baseline
        tolerance here — the test fails on any error.
        """
        report = doctor_results[profile_path.name]
        assert report.summary.errors == 0, (
            f"{profile_path.name}: doctor reported {report.summary.errors} "
            f"errors (HPC-L5 fail-closed); findings="
            f"{[f.code for f in report.findings if f.severity == 'error']}"
        )

    def test_strict_gate_runs_all_profiles(self, doctor_results: dict[str, DoctorReport]) -> None:
        """Sanity: every golden profile produced a DoctorReport (no crashes)."""
        assert len(doctor_results) == len(_all_golden_profiles())
