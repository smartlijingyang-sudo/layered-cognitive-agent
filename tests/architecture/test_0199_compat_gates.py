"""PR-0199-P1-14 — ADR-0199 §11 HPC-L2 + §12.1 COMPAT inventory tests.

Pins the two new audit kinds added by P1-14:

- ``facade_bypass`` — ``resolve_profile`` / ``compile_plan`` calls outside
  the ``lca/application/runtime/`` facade (HPC-L2).
- ``intent_construction_outside_adapters`` — ``RunIntent(...)``
  constructions outside the L1 adapters + facade (I-HPC-1).

The tests pin three properties of the audit kinds:

1. The script runs clean end-to-end (exit 0, JSON-parseable) — fixes
   the P1-12 baseline failure where the script's audit helpers
   imported stale paths out of ``lca.harness.diagnostics``.
2. The production-path L0 handlers / CLI runs-create file are free of
   facade_bypass findings — pins the P1-11 + P1-13 deliveries.
3. The exempt paths (adapters / facade / tests / harness / scripts /
   vendor / lca_kernel) are not flagged — pins the scan's exempt set.

AST detection is in-process for tests 5–9 (so we can inject a temp
``.py`` file and assert exactly one finding), subprocess for tests
1–4 + 10 (so we exercise the same ``python scripts/<name>.py --json``
entry point the rest of CI uses).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "route_legacy_patterns.py"

# L0 handler audited by ADR-0199 §11 HPC-L2 (P1-11 delivery).
HANDLERS_ROOT = REPO / "lca" / "plugins" / "transport" / "webserver" / "handlers"
# CLI runs-create handler audited by P1-13.
CLI_RUNS_CREATE = REPO / "lca" / "infrastructure" / "cli" / "commands" / "runs" / "runs.py"


# ── Subprocess helper ────────────────────────────────────────────────


def _run_script_json(timeout: int = 60) -> dict:
    """Invoke ``scripts/route_legacy_patterns.py --json`` as a subprocess
    and return the parsed JSON payload.

    Uses the same Python interpreter pytest is running under, matching
    the verify matrix in the brief. The script has no dependencies
    beyond the in-repo ``lca`` package, so no extra venv setup is
    required.
    """
    result = subprocess.run(  # noqa: S603 — intentional subprocess call
        [sys.executable, str(SCRIPT), "--json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, (
        f"scripts/route_legacy_patterns.py exited {result.returncode}.\nstderr:\n{result.stderr}"
    )
    return json.loads(result.stdout)


# ── Tests 1–4: subprocess end-to-end ────────────────────────────────


def test_route_legacy_patterns_runs_clean() -> None:
    """#1: ``scripts/route_legacy_patterns.py --json`` exits 0 and emits
    valid JSON. Pins the P1-12 baseline fix (audit helpers moved out of
    ``lca.harness.diagnostics``).
    """
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), "--json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"scripts/route_legacy_patterns.py exited {result.returncode}; stderr:\n{result.stderr}"
    )
    payload = json.loads(result.stdout)  # raises on non-JSON
    assert isinstance(payload, dict)
    assert "total" in payload
    assert "by_kind" in payload
    assert "by_owner" in payload
    # The two new audit kinds are registered (even if they have zero
    # findings under the current tree for some paths).
    assert "facade_bypass" in payload["by_kind"]
    assert "intent_construction_outside_adapters" in payload["by_kind"]


def test_route_legacy_patterns_reports_no_facade_bypass_in_handlers() -> None:
    """#2: no ``facade_bypass`` findings under
    ``lca/plugins/transport/webserver/handlers/`` (P1-11 delivery).
    """
    payload = _run_script_json()
    handlers_hits = [
        v
        for v in payload["by_kind"].get("facade_bypass", [])
        if HANDLERS_ROOT.as_posix() in v["path"]
    ]
    assert handlers_hits == [], (
        "L0 handlers must NOT call resolve_profile / compile_plan "
        "(ADR-0199 §11 HPC-L2; P1-11 delivery). Offenders:\n"
        + "\n".join(f"  {v['path']}:{v['line']} {v['kind']}" for v in handlers_hits)
    )


def test_route_legacy_patterns_reports_no_facade_bypass_in_cli() -> None:
    """#3: no ``facade_bypass`` findings against the CLI runs-create
    production handler (P1-13 delivery). Narrower than the broad
    ``lca/infrastructure/cli/commands/`` tree because the diagnostic /
    profile / kernel commands legitimately call resolve_profile +
    compile_plan for read-only paths (covered by ADR-0199 §5 Doctor;
    out of scope for HPC-L2 production-path gate).
    """
    payload = _run_script_json()
    cli_run_create_hits = [
        v
        for v in payload["by_kind"].get("facade_bypass", [])
        if Path(v["path"]).resolve() == CLI_RUNS_CREATE
    ]
    assert cli_run_create_hits == [], (
        "CLI runs create handler must NOT call resolve_profile / "
        "compile_plan directly (ADR-0199 §11 HPC-L2; P1-13 delivery). "
        "Offenders:\n"
        + "\n".join(f"  {v['path']}:{v['line']} {v['kind']}" for v in cli_run_create_hits)
    )


def test_route_legacy_patterns_reports_no_intent_construction_outside_adapters() -> None:
    """#4: zero ``intent_construction_outside_adapters`` findings on the
    current tree. The canonical ``RunIntent`` is only constructed in
    ``lca/application/runtime/adapters/`` + ``default_facade.py``; tests
    in ``tests/**`` and a local-carrier ``RunIntent`` in
    ``lca/plugins/transport/.../intent.py`` are correctly excluded.
    """
    payload = _run_script_json()
    findings = payload["by_kind"].get("intent_construction_outside_adapters", [])
    assert findings == [], (
        "RunIntent must only be constructed in lca/application/runtime/"
        "adapters/ + default_facade.py (ADR-0199 §10 I-HPC-1). Offenders:\n"
        + "\n".join(f"  {v['path']}:{v['line']} {v['kind']}" for v in findings)
    )


# ── Tests 5–9: in-process AST scan with fixture files ──────────────


@pytest.fixture
def script_scan_module():
    """Import the script as a module so we can call its scan helpers
    with a fixture root (the script's module-level ``_REPO`` is fixed,
    but its scan helpers accept an explicit ``repo: Path``).
    """
    # Add the repo root so ``scripts.route_legacy_patterns`` resolves.
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    # The script is importable as ``scripts.route_legacy_patterns``.
    from scripts import route_legacy_patterns as mod

    return mod


def test_route_legacy_patterns_finds_intentional_violation(
    tmp_path: Path, script_scan_module
) -> None:
    """#5: drop a fixture ``.py`` file containing ``resolve_profile(
    "/path")`` under a synthetic tree; the scan reports exactly one
    facade_bypass finding.
    """
    synthetic_repo = tmp_path / "repo"
    lca_root = synthetic_repo / "lca"
    lca_root.mkdir(parents=True)
    bad_file = lca_root / "violator.py"
    bad_file.write_text(
        "def handler():\n"
        "    from lca.harness.profile.resolve.resolve import resolve_profile\n"
        "    return resolve_profile('/profiles/web-standard.yaml')\n",
        encoding="utf-8",
    )
    findings = script_scan_module._scan_facade_bypass(synthetic_repo)
    # At least one hit, and every hit points at our fixture file.
    assert len(findings) >= 1, "scanner did not detect the intentional violation"
    matching = [f for f in findings if Path(f.path).resolve() == bad_file.resolve()]
    assert len(matching) == 1, (
        f"expected exactly one finding at {bad_file}, got {len(matching)}: {findings}"
    )
    assert matching[0].kind == "facade_bypass::resolve_profile"


def test_route_legacy_patterns_adapters_are_exempt(tmp_path: Path, script_scan_module) -> None:
    """#6: a fixture file under ``lca/application/runtime/adapters/``
    calling ``RunIntent(...)`` is NOT flagged (the adapters are the
    canonical construction site per I-HPC-1).
    """
    synthetic_repo = tmp_path / "repo"
    adapters_dir = synthetic_repo / "lca" / "application" / "runtime" / "adapters"
    adapters_dir.mkdir(parents=True)
    adapter_file = adapters_dir / "fixture_adapter.py"
    adapter_file.write_text(
        "from lca.contracts.runtime.intent import RunIntent\n"
        "def build():\n"
        "    return RunIntent(\n"
        "        profile_path='p.yaml',\n"
        "        user_text='x',\n"
        "        mode='solo',\n"
        "        session_id=None,\n"
        "        assistant_id=None,\n"
        "        attachment_ids=(),\n"
        "        prior_turns=(),\n"
        "        execution_target='local',\n"
        "        options={},\n"
        "        surface='test',\n"
        "    )\n",
        encoding="utf-8",
    )
    findings = script_scan_module._scan_intent_construction_outside_adapters(synthetic_repo)
    adapter_findings = [f for f in findings if Path(f.path).resolve() == adapter_file.resolve()]
    assert adapter_findings == [], (
        "adapters/ must be exempt from intent_construction_outside_adapters "
        f"(I-HPC-1). Found: {adapter_findings}"
    )


def test_route_legacy_patterns_facade_is_exempt(tmp_path: Path, script_scan_module) -> None:
    """#7: ``default_facade.py`` is exempt — the facade may construct
    ``RunIntent`` as part of its responsibility.
    """
    synthetic_repo = tmp_path / "repo"
    runtime_dir = synthetic_repo / "lca" / "application" / "runtime"
    runtime_dir.mkdir(parents=True)
    facade_file = runtime_dir / "default_facade.py"
    facade_file.write_text(
        "from lca.contracts.runtime.intent import RunIntent\n"
        "def build():\n"
        "    return RunIntent(\n"
        "        profile_path='p.yaml',\n"
        "        user_text='x',\n"
        "        mode='solo',\n"
        "        session_id=None,\n"
        "        assistant_id=None,\n"
        "        attachment_ids=(),\n"
        "        prior_turns=(),\n"
        "        execution_target='local',\n"
        "        options={},\n"
        "        surface='test',\n"
        "    )\n",
        encoding="utf-8",
    )
    findings = script_scan_module._scan_intent_construction_outside_adapters(synthetic_repo)
    facade_findings = [f for f in findings if Path(f.path).resolve() == facade_file.resolve()]
    assert facade_findings == [], (
        "default_facade.py must be exempt from intent_construction_"
        f"outside_adapters (I-HPC-1). Found: {facade_findings}"
    )


def test_route_legacy_patterns_tests_are_exempt(tmp_path: Path, script_scan_module) -> None:
    """#8: a fixture ``tests/`` tree is exempt from both audit kinds —
    test code may call resolve_profile / compile_plan / construct
    RunIntent freely (no production-path concern).
    """
    synthetic_repo = tmp_path / "repo"
    tests_dir = synthetic_repo / "tests"
    tests_dir.mkdir(parents=True)
    test_file = tests_dir / "fixture_test.py"
    test_file.write_text(
        "from lca.contracts.runtime.intent import RunIntent\n"
        "from lca.harness.profile.resolve.resolve import resolve_profile\n"
        "from lca.harness.composition.plan_compiler import compile_plan\n"
        "def test_x():\n"
        "    p = resolve_profile('/profiles/x.yaml')\n"
        "    plan = compile_plan(p)\n"
        "    intent = RunIntent(\n"
        "        profile_path='p.yaml', user_text='x', mode='solo',\n"
        "        session_id=None, assistant_id=None, attachment_ids=(),\n"
        "        prior_turns=(), execution_target='local', options={},\n"
        "        surface='test',\n"
        "    )\n",
        encoding="utf-8",
    )
    facade_findings = script_scan_module._scan_facade_bypass(synthetic_repo)
    intent_findings = script_scan_module._scan_intent_construction_outside_adapters(synthetic_repo)
    test_facade_hits = [f for f in facade_findings if Path(f.path).resolve() == test_file.resolve()]
    test_intent_hits = [f for f in intent_findings if Path(f.path).resolve() == test_file.resolve()]
    assert test_facade_hits == [], (
        f"tests/ must be exempt from facade_bypass. Found: {test_facade_hits}"
    )
    assert test_intent_hits == [], (
        f"tests/ must be exempt from intent_construction_outside_adapters. "
        f"Found: {test_intent_hits}"
    )


def test_route_legacy_patterns_helpers_are_exempt(tmp_path: Path, script_scan_module) -> None:
    """#9: a fixture file under ``lca/harness/`` calling ``resolve_profile``
    / ``compile_plan`` is exempt — harness IS the canonical home of
    those symbols (they are *defined* there).
    """
    synthetic_repo = tmp_path / "repo"
    harness_dir = synthetic_repo / "lca" / "harness" / "profile"
    harness_dir.mkdir(parents=True)
    helper_file = harness_dir / "fixture_helper.py"
    helper_file.write_text(
        "from lca.harness.profile.resolve.resolve import resolve_profile\n"
        "from lca.harness.composition.plan_compiler import compile_plan\n"
        "def helper():\n"
        "    p = resolve_profile('/profiles/x.yaml')\n"
        "    return compile_plan(p)\n",
        encoding="utf-8",
    )
    findings = script_scan_module._scan_facade_bypass(synthetic_repo)
    helper_findings = [f for f in findings if Path(f.path).resolve() == helper_file.resolve()]
    assert helper_findings == [], (
        f"lca/harness/** must be exempt from facade_bypass. Found: {helper_findings}"
    )


# ── Test 10: full-tree clean exit ──────────────────────────────────


def test_route_legacy_patterns_exit_zero_on_clean_tree() -> None:
    """#10: the script exits 0 against the current tree (the script is
    a *router*, not a gate — see its module docstring). The exit-zero
    invariant is what we want to pin here; the per-kind finding count
    is informational only.
    """
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"scripts/route_legacy_patterns.py exited {result.returncode}; stderr:\n{result.stderr}"
    )
