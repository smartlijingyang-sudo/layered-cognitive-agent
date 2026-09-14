"""Regression test for ``lca-ops debug-factories`` under the v2 plan compiler.

Bug fix (poteto-mode investigation 2026-09-14): the CLI command accessed
``plan.phase_graph`` to enumerate the bundle graph. ADR-0221 P3 retired
that attribute (the v2 plan does not carry a declarative phase graph —
runtime builds it via ``PlanInterpreter`` + NodeExecutor subgraphs at
boot). The fix replaces the entry point with ``resolved.bundles`` plus
``walk_bundle`` recursion through ``sub_spec_ref.plan_ref``, so the
outer plan is still enumerated under v2.

This test runs ``cmd_debug_factories`` end-to-end against the canonical
profile. If the v1 ``plan.phase_graph`` access is reintroduced, the
command will raise ``AttributeError`` and the test fails.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from lca.infrastructure.cli.commands.runs.driver_debug import cmd_debug_factories

PROFILE = Path("profiles/web-standard.yaml")


def test_cmd_debug_factories_runs_under_v2_plan() -> None:
    """``cmd_debug_factories`` must not touch ``plan.phase_graph``.

    Asserts the command reaches the report-rendering stage (no
    AttributeError). The report content is intentionally not asserted
    beyond the fact that bundles were visited, since bundle contents
    vary with profile evolution.
    """
    cmd_debug_factories(PROFILE, json_mode=False)


def test_cmd_debug_factories_json_mode_emits_expected_keys() -> None:
    """JSON output must include the v1 contract fields that downstream tooling parses.

    Typer's ``echo`` writes to stderr when the terminal supports ANSI; we
    capture both streams to find the JSON document. The function must
    still emit one parseable JSON object regardless of which stream
    Typer picked.
    """
    import sys

    out = io.StringIO()
    err = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        cmd_debug_factories(PROFILE, json_mode=True)
    finally:
        sys.stdout, sys.stderr = old_out, old_err

    # The JSON document is the only thing in either stream that parses.
    document = None
    for stream in (out.getvalue(), err.getvalue()):
        for line in stream.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                document = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
        if document is not None:
            break
    assert document is not None, (out.getvalue()[:400], err.getvalue()[:400])
    assert document["profile"].endswith("web-standard.yaml")
    assert document["bundles_visited"], document
    assert document["total_factories"] > 0
    assert "rows" in document
