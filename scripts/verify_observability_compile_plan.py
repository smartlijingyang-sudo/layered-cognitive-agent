#!/usr/bin/env python3
"""Compile and validate observability yaml SSOT (ADR-0198).

Exit 0 when compile plan has no error-severity diagnostics; 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from lca_kernel.events.compile.compiler import ObservabilityCompiler

_REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate observability compile plan")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=_REPO / "lca_kernel" / "events" / "config",
        help="Observability config root",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable report")
    args = parser.parse_args()

    plan = ObservabilityCompiler.compile(args.config_dir)
    report = {
        "ok": plan.ok,
        "schema_version": plan.schema_version,
        "closure_events": len(plan.closure_events),
        "projections": len(plan.projections),
        "outputs": len(plan.outputs),
        "diagnostics": [asdict(d) for d in plan.diagnostics],
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"observability compile plan: {'OK' if plan.ok else 'FAILED'}")
        print(f"  closure_events={len(plan.closure_events)} projections={len(plan.projections)}")
        for diag in plan.diagnostics:
            print(f"  [{diag.severity}] {diag.code}: {diag.message}")
            if diag.path:
                print(f"           at {diag.path}")

    return 0 if plan.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
