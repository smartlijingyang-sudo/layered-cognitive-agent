"""``runtime`` must stay importable in every layer-edge import order.

``_run_inspect_internal`` used to import ``enrich_inspect_profile`` and
``get_run_workspace`` lazily (RA-020). The deferred imports carried an
implicit claim that module-level imports would cycle; a fresh-interpreter
probe refuted it (three orders: routing-first / runtime-first /
workspace-first, all clean), so the imports now live at module top.

These tests pin that evidence: if a future change reintroduces a cycle
between ``lca.infrastructure.sandbox.runtime.runtime``,
``lca.infrastructure.skills.format.routing`` and
``lca.infrastructure.workspace``, each import order fails in its own
fresh interpreter instead of being masked by whatever an earlier test in
the same process already imported (the pytest-collection masking that
``test_run_paths_import_order.py`` documents).
"""

from __future__ import annotations

import subprocess
import sys

ROUTING = "lca.infrastructure.skills.format.routing"
RUNTIME = "lca.infrastructure.sandbox.runtime.runtime"
WORKSPACE = "lca.infrastructure.workspace"


def _import_order(*modules: str) -> None:
    stmt = "; ".join(f"import {m}" for m in modules) + "; print('ok')"
    result = subprocess.run(  # noqa: S603 - executable and module names are fixed literals
        [sys.executable, "-c", stmt],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"import order {modules} failed:\n{result.stderr[-2000:]}"
    )
    assert result.stdout.strip() == "ok"


def test_routing_first_then_runtime_then_workspace() -> None:
    _import_order(ROUTING, RUNTIME, WORKSPACE)


def test_runtime_first_then_routing_then_workspace() -> None:
    _import_order(RUNTIME, ROUTING, WORKSPACE)


def test_workspace_first_then_runtime_then_routing() -> None:
    _import_order(WORKSPACE, RUNTIME, ROUTING)
