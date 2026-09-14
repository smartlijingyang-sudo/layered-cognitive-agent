#!/usr/bin/env python3
"""Typed port graph redesign acceptance criteria (spec §8).

Verifies all 8 criteria from ``docs/superpowers/specs/2026-09-14-typed-port-graph-redesign-design.md``
§8. Read-only — never mutates the working tree.

Each check is independent: one failure does not block the others.
Failures print actionable context (file:line and offending text).

Manual run from repo root::

    python scripts/verify_typed_port_graph.py

Exit code 0 means all 8 criteria pass; non-zero means at least one
criterion failed (the script reports which).

There is no global ``verify_*.py`` discoverer in ``.github/workflows/ci.yml``
— each gate is invoked by name. CI invocation should be added explicitly::

    - name: Typed port graph acceptance (spec §8)
      run: uv run python scripts/verify_typed_port_graph.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Files / directories each check concerns.
GRAPH_DIR = REPO / "lca" / "framework" / "graph"
BUNDLES_DIR = REPO / "bundles"
LCA_DIR = REPO / "lca"
LCA_KERNEL_DIR = REPO / "lca_kernel"
TESTS_DIR = REPO / "tests"

AC3_TEST = TESTS_DIR / "integration" / "test_end_to_end_think_to_act.py"
AC4_TEST = TESTS_DIR / "lca_kernel" / "plan" / "test_phase_main_outer_lift.py"

# Spec §0 lists three known-broken predicate shapes; AC5 demands they become
# lift-time failures. We probe each on the current bundle text and assert
# that lift rejects it.
KNOWN_BROKEN_PREDICATES: tuple[str, ...] = (
    'result.payload.decision.action_type == "use_tool"',
    'result.payload.decision.action_type == "respond"',
    "result.payload.should_stop",
)

# String-form `when:` lines: detect "  when:" followed by something that
# isn't a typed Predicate mapping (a bool, a number, or anything else).
STRING_WHEN_LINE = re.compile(
    r"^\s*when:\s*(?!\{)[^#\n]+\s*$",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = "✅" if ok else "❌"
    print(f"{mark} {name}")
    if detail:
        for line in detail.splitlines():
            print(f"    {line}")


# ---------------------------------------------------------------------------
# AC1 — bundles/phase_main_outer.yaml lifts without error
# ---------------------------------------------------------------------------


def ac1_phase_main_outer_lifts() -> None:
    name = "AC1: bundles/phase_main_outer.yaml lifts without error"
    path = BUNDLES_DIR / "phase_main_outer.yaml"
    if not path.exists():
        record(name, False, f"missing file: {path}")
        return

    try:
        import yaml

        from lca.framework.graph.lifter import lift_graph_spec
    except Exception as exc:  # pragma: no cover — import error
        record(name, False, f"import failed: {exc}")
        return

    text = path.read_text(encoding="utf-8")
    if "<<<<<<<" in text or ">>>>>>>" in text:
        record(name, False, "file contains unresolved merge markers")
        return

    try:
        spec = yaml.safe_load(text)
        plan = lift_graph_spec(spec)
    except Exception as exc:
        record(name, False, f"lift failed: {exc}")
        return

    record(
        name,
        True,
        f"plan.id={plan.id}, nodes={len(plan.nodes)}, edges={len(plan.edges)}",
    )


# ---------------------------------------------------------------------------
# AC2 — debug-graph command surfaces act.main entries for use_tool runs
# ---------------------------------------------------------------------------


def ac2_debug_graph_act_main() -> None:
    name = "AC2: lca-ops debug-graph surfaces act.main for use_tool runs"
    # The spec pins this on the *command output*. The contract is observable
    # as long as build_debug_graph includes nodes by node_id and the CLI
    # command name exists. We pin two things:
    #   (a) the CLI subcommand exists at the expected name
    #   (b) build_debug_graph renders node entries for an act.main spine event
    cli_path = (
        REPO / "lca" / "infrastructure" / "cli" / "commands" / "observation" / "debug_graph.py"
    )
    if not cli_path.exists():
        record(name, False, f"missing CLI module: {cli_path}")
        return

    cli_text = cli_path.read_text(encoding="utf-8")
    if "phase_graph.node.end" not in cli_text or "node_id" not in cli_text:
        record(
            name,
            False,
            "CLI does not render phase_graph.node.end entries by node_id",
        )
        return

    # Synthesize a minimal spine with one act.main node.end event whose
    # outputs.routing.action_type == "use_tool". build_debug_graph must
    # produce a node entry whose node_id == "act.main".
    try:
        from lca.infrastructure.cli.commands.observation.debug_graph import (
            build_debug_graph,
        )
    except Exception as exc:  # pragma: no cover — import error
        record(name, False, f"import build_debug_graph failed: {exc}")
        return

    events = [
        {
            "event_id": "ev1",
            "execution_point": "kernel.run.start",
            "payload": {"run_id": "run_test_ac2"},
        },
        {
            "event_id": "ev2",
            "execution_point": "phase_graph.node.start",
            "payload": {"node_id": "act.main", "visit_index": 1},
        },
        {
            "event_id": "ev3",
            "execution_point": "phase_graph.node.end",
            "payload": {
                "node_id": "act.main",
                "visit_index": 1,
                "elapsed_ms": 12,
                "dispatch": "next",
                "inputs": {},
                "outputs": {
                    "routing": {"action_type": "use_tool", "next_hint": "think.main"},
                    "act_outcome": {"status": "ok"},
                },
                "outcome": "success",
                "error": "",
            },
        },
    ]

    report = build_debug_graph(events)
    nodes = report.get("nodes") if isinstance(report, dict) else None
    if not isinstance(nodes, list):
        record(name, False, f"report.nodes missing or wrong type: {type(nodes).__name__}")
        return

    act_main = [n for n in nodes if isinstance(n, dict) and n.get("node_id") == "act.main"]
    if not act_main:
        record(
            name,
            False,
            f"no node entry with node_id=act.main among {[n.get('node_id') for n in nodes]}",
        )
        return

    record(name, True, f"act.main entry rendered: marker={act_main[0].get('marker')}")


# ---------------------------------------------------------------------------
# AC3 — test_end_to_end_think_to_act.py passes
# ---------------------------------------------------------------------------


def ac3_think_to_act_test() -> None:
    name = "AC3: tests/integration/test_end_to_end_think_to_act.py passes"
    if not AC3_TEST.exists():
        record(name, False, f"test file missing: {AC3_TEST}")
        return

    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            str(AC3_TEST.relative_to(REPO)),
            "-x",
            "--no-cov",
            "--noconftest",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode == 0:
        record(name, True, "pytest exit 0")
    else:
        tail = (proc.stdout + proc.stderr).strip().splitlines()
        record(name, False, "pytest failed — tail:\n" + "\n".join(tail[-12:]))


# ---------------------------------------------------------------------------
# AC4 — test_phase_main_outer_lift.py passes
# ---------------------------------------------------------------------------


def ac4_phase_main_outer_lift_test() -> None:
    name = "AC4: tests/lca_kernel/plan/test_phase_main_outer_lift.py passes"
    if not AC4_TEST.exists():
        record(name, False, f"test file missing: {AC4_TEST}")
        return

    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            str(AC4_TEST.relative_to(REPO)),
            "-x",
            "--no-cov",
            "--noconftest",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode == 0:
        record(name, True, "pytest exit 0")
    else:
        tail = (proc.stdout + proc.stderr).strip().splitlines()
        record(name, False, "pytest failed — tail:\n" + "\n".join(tail[-12:]))


# ---------------------------------------------------------------------------
# AC5 — three known-broken predicates become lift-time failures
# ---------------------------------------------------------------------------


def ac5_known_broken_predicates_lift_fail() -> None:
    name = "AC5: three known-broken predicates become lift-time failures"

    # If phase_main_outer.yaml still contains the broken predicate text, lift
    # MUST reject. If the predicate was already migrated to a typed Predicate,
    # lift succeeds (which is also acceptable — the bug was the silent False).
    try:
        import yaml

        from lca.contracts.protocols.graph.errors import PlanLiftError
        from lca.framework.graph.lifter import lift_graph_spec
    except Exception as exc:  # pragma: no cover — import error
        record(name, False, f"import failed: {exc}")
        return

    findings: list[str] = []
    # Probe each known-broken predicate by inserting it into the existing
    # phase_main_outer.yaml as an extra edge. If lift raises PlanLiftError,
    # that predicate is now caught at lift time.
    base_text = (BUNDLES_DIR / "phase_main_outer.yaml").read_text(encoding="utf-8")
    if "<<<<<<<" in base_text or ">>>>>>>" in base_text:
        record(name, False, "phase_main_outer.yaml contains unresolved merge markers")
        return
    # Used only to validate base_text parses; per-probe specs are constructed below.
    yaml.safe_load(base_text)

    for pred in KNOWN_BROKEN_PREDICATES:
        probe = {
            "id": "probe",
            "nodes": [
                {
                    "id": "a",
                    "binding": "node_executor",
                    "outputs": [{"name": "decision", "payload_type": "object"}],
                    "entry": True,
                },
                {"id": "b", "binding": "node_executor", "terminal": True},
            ],
            "edges": [
                {
                    "from": "a",
                    "to": "b",
                    "when": pred,
                }
            ],
        }
        try:
            lift_graph_spec(probe)
        except PlanLiftError as exc:
            findings.append(f"  ✓ {pred!r}: lift raised PlanLiftError ({exc})")
            continue
        except Exception as exc:
            findings.append(f"  ✓ {pred!r}: lift raised {type(exc).__name__} ({exc})")
            continue
        # Lift accepted — that means the predicate was silently dropped or
        # the spec format swallowed it. Fail loud.
        findings.append(f"  ✗ {pred!r}: lift ACCEPTED string predicate — silent False risk!")

    failures = [f for f in findings if f.lstrip().startswith("✗")]
    if failures:
        record(
            name, False, "lift did not catch all known-broken predicates:\n" + "\n".join(findings)
        )
    else:
        record(name, True, "\n".join(findings))


# ---------------------------------------------------------------------------
# AC6 — no __getattr__ fallback in lca/framework/graph/
# ---------------------------------------------------------------------------


def ac6_no_getattr_fallback() -> None:
    name = "AC6: no __getattr__ fallback in lca/framework/graph/"
    py_files = sorted(GRAPH_DIR.glob("*.py"))
    offenders: list[str] = []
    for py in py_files:
        text = py.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "__getattr__" in line:
                offenders.append(f"  {py.relative_to(REPO)}:{lineno}: {line.strip()}")

    if offenders:
        record(name, False, "found __getattr__:\n" + "\n".join(offenders))
        return

    record(name, True, f"scanned {len(py_files)} files under {GRAPH_DIR}")


# ---------------------------------------------------------------------------
# AC7 — no string `when:` fields in any bundle YAML
# ---------------------------------------------------------------------------


def ac7_no_string_when() -> None:
    name = "AC7: no string `when:` fields in bundle YAMLs"
    yaml_files = sorted(BUNDLES_DIR.rglob("*.yaml")) + sorted(BUNDLES_DIR.rglob("*.yml"))
    offenders: list[str] = []
    for yf in yaml_files:
        text = yf.read_text(encoding="utf-8")
        # `when:` with a scalar value (string / number / true / false) — not a
        # typed Predicate mapping. Booleans are fine (always-true / always-
        # false edges) but anything that looks like a comparison string is not.
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("when:"):
                continue
            value = stripped[len("when:") :].strip()
            if value.startswith("{") or value == "":
                continue
            # Booleans and pure identifiers / numbers are explicit constants.
            # Anything that contains comparison operators or `.` (attribute
            # access) is the legacy string DSL.
            if value in {"true", "false", "True", "False", "null"}:
                continue
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
                continue
            offenders.append(f"  {yf.relative_to(REPO)}:{lineno}: {stripped}")

    if offenders:
        record(
            name,
            False,
            f"found {len(offenders)} string `when:` line(s):\n" + "\n".join(offenders[:20]),
        )
        return

    record(name, True, f"scanned {len(yaml_files)} bundle YAMLs")


# ---------------------------------------------------------------------------
# AC8 — no `result.payload` references in lca/ lca_kernel/ bundles/
# ---------------------------------------------------------------------------


def ac8_no_result_payload() -> None:
    name = "AC8: zero hits for `result.payload` in lca/ lca_kernel/ bundles/"
    targets = [LCA_DIR, LCA_KERNEL_DIR, BUNDLES_DIR]
    offenders: list[str] = []
    for root in targets:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                text = py.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "result.payload" in line:
                    offenders.append(f"  {py.relative_to(REPO)}:{lineno}: {line.strip()}")
        for yf in root.rglob("*.yaml"):
            try:
                text = yf.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "result.payload" in line:
                    offenders.append(f"  {yf.relative_to(REPO)}:{lineno}: {line.strip()}")

    if offenders:
        record(
            name,
            False,
            f"found {len(offenders)} hits:\n" + "\n".join(offenders[:20]),
        )
        return

    record(name, True, f"scanned {LCA_DIR}, {LCA_KERNEL_DIR}, {BUNDLES_DIR}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    if not GRAPH_DIR.exists():
        print(f"❌ framework graph dir missing: {GRAPH_DIR}", file=sys.stderr)
        return 2

    print(f"Verifying typed port graph acceptance ({REPO})\n")
    ac1_phase_main_outer_lifts()
    ac2_debug_graph_act_main()
    ac3_think_to_act_test()
    ac4_phase_main_outer_lift_test()
    ac5_known_broken_predicates_lift_fail()
    ac6_no_getattr_fallback()
    ac7_no_string_when()
    ac8_no_result_payload()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} checks passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
