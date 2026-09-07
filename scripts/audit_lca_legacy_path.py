#!/usr/bin/env python3
"""Spec §10.3: fail the build when retired P1 symbols leak back (PR-4 gate)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RETIRED = {
    "modules": [
        "lca.plugins.transport.webserver.handlers.runs.api.legacy_dispatcher_adapter",
        "lca.plugins.transport.webserver.handlers.runs.terminal.legacy.adapter",
        "lca.plugins.transport.run_ui_encoder__encoder_provider",
        "lca.plugins.transport.run_live_observe__seam",
    ],
    "files": [
        "lobehub-ui/src/store/chat/agents/transports/lcaRunObserve.ts",
        "lobehub-ui/src/store/chat/agents/transports/lcaRunHil.ts",
        "lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts",
        "lobehub-ui/src/store/chat/agents/transports/LcaRunDriver.ts",
        "lobehub-ui/src/store/chat/agents/transports/lcaRunCommand.ts",
        "deploy/lobehub/patches/runtime/lca_run_driver.py",
    ],
    "symbols": [
        "LegacyRunDispatcher",
        "RunUiEncoder",
        "LCA_RUNTIME_FACADE",
    ],
    "env_flags": [
        "LCA_RUNTIME_FACADE",
    ],
}

_IGNORE_GLOBS = [
    "!**/__pycache__/**",
    "!**/node_modules/**",
    "!scripts/audit_lca_legacy_path.py",
    "!tests/architecture/test_audit_lca_legacy_path.py",
    "!docs/**",
]


def _rg(pattern: str, paths: list[str]) -> list[str]:
    flat: list[str] = ["rg", "--line-number", pattern, *paths]
    for g in _IGNORE_GLOBS:
        flat.extend(["--glob", g])
    res = subprocess.run(flat, cwd=str(ROOT), capture_output=True, text=True)  # noqa: S603
    if res.returncode > 1:
        print(f"rg error: {res.stderr}", file=sys.stderr)
        sys.exit(2)
    return [line for line in res.stdout.splitlines() if line.strip()]


def main() -> int:
    failures: list[str] = []

    for rel in RETIRED["files"]:
        if (ROOT / rel).is_file():
            failures.append(f"file still present: {rel}")

    search_paths = ["lca", "deploy/lobehub", "bundles"]
    lobehub = ROOT / "lobehub-ui"
    if lobehub.is_dir():
        search_paths.extend(["lobehub-ui/src", "lobehub-ui/apps", "lobehub-ui/packages"])

    for module in RETIRED["modules"]:
        pattern = module.replace(".", r"\.")
        for hit in _rg(pattern, search_paths):
            if "/tests/" in hit.replace("\\", "/") and "archived" not in hit:
                continue
            failures.append(f"retired module {module}: {hit}")

    for sym in RETIRED["symbols"]:
        for hit in _rg(rf"\b{sym}\b", search_paths):
            failures.append(f"retired symbol {sym}: {hit}")

    for env in RETIRED["env_flags"]:
        for hit in _rg(env, search_paths):
            failures.append(f"retired env {env}: {hit}")

    if failures:
        print("FAIL: retired LCA symbols still referenced:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("OK: no retired LCA symbols referenced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
