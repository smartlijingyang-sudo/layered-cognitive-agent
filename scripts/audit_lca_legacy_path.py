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
    # ADR-0200 §1 + §6.1.2 + PR-3 wire-parity post-mortem.
    # LCA's front-end chat transport MUST NOT import the upstream
    # AgentStreamClient: its buildWsUrl() emits `<base>/ws?operationId=...`
    # which is the lobehub-native gateway wire path, not LCA's
    # `/v1/runs/{run_id}/ws`. Re-using it produced the PR-3 silent
    # mismatch where chat silently fell back to /webapi/chat/<provider>.
    # See tests/architecture/test_lca_wire_parity.py for the SSOT guard.
    "forbidden_imports": [
        # Match a value import of the AgentStreamClient class only.
        # `import type { AgentStreamEvent }` (event shapes) is fine — those
        # mirror the wire schema and have no path-pinning. The bug is
        # `import { AgentStreamClient }` because the class hard-codes the
        # upstream `<base>/ws?operationId=...` URL.
        ("lobehub-ui/src/store/chat/agents/transports/lcaGateway",
         r"^\s*import\s*\{[^}]*\bAgentStreamClient\b",
         "value import of upstream AgentStreamClient in lcaGateway/* — wire path mismatch, use LcaAgentStreamClient instead"),
        ("lobehub-ui/src/store/chat/agents/transports/lcaGateway",
         r"new\s+AgentStreamClient\b",
         "construction of upstream AgentStreamClient in lcaGateway/* — wire path mismatch, use LcaAgentStreamClient instead"),
    ],
    # The original native chat dispatch path (`/webapi/chat/<provider>`)
    # is retired from LCA's runtime; streamingExecutor.ts has a hard
    # fail when isLcaGatewayMode() is false. We don't add a separate
    # path audit here because the streamingExecutor hard fail + the
    # `lcaGateway` value-import rule above already block reintroduction;
    # a noisy false-positive on comments is worse than the gap.
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

    for rel_dir, pattern, why in RETIRED.get("forbidden_imports", []):
        # Constrain the ripgrep to the directory so we don't false-positive
        # on the patch source mirror under deploy/lobehub/patches/...
        scoped = [rel_dir]
        for hit in _rg(pattern, scoped):
            failures.append(f"{why}: {hit}")

    if failures:
        print("FAIL: retired LCA symbols still referenced:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("OK: no retired LCA symbols referenced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
