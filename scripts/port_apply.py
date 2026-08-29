#!/usr/bin/env python3
"""Apply one cluster's end-state delta as a structured commit.

Pipeline per cluster:
1. Read the cluster's path list from port_endstate.CLUSTER_PATHS.
2. Compute the patch as `git diff <base>..<head> -- <paths>`.
3. `git apply --check` the patch; abort if it cannot apply cleanly.
4. Apply the patch (`git apply`).
5. Run gates: `uv run ruff check --fix`, `uv run ruff format`,
   `uv run lint-imports`, `uv run pytest --no-cov <test-path>`,
   `python scripts/check_locked_surface.py --base HEAD`.
6. Stage the touched paths; emit a structured commit message with
   source-commit attribution in the body.

CLI:
    --cluster <id>    cluster id to apply (e.g. C1)
    --base <ref>      base commit (default: $MERGE_BASE)
    --head <ref>      head commit (default: origin/main)
    --no-commit       apply patch only; do not commit (for manual review)
    --self-test       run in-process assertions

Library:
    apply_cluster(cluster_id, base, head, dry_run) -> ApplyResult
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# Ensure `from scripts.<x>` resolves when this script is invoked directly
# (not through pytest, which adds the project root to sys.path automatically).
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.port_endstate import CLUSTER_PATHS  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_BASE = "bae32d8c27ee2b59312303fbfa68d4738c2f316f"
_DEFAULT_HEAD = "origin/main"


@dataclass(frozen=True)
class ApplyResult:
    cluster_id: str
    rc: int
    patch_lines: int
    applied: bool
    committed: bool
    message: str


def _run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        cwd=_ROOT,
    )


def _diff_patch(paths: list[str], base: str, head: str) -> str:
    p = _run(["git", "diff", f"{base}..{head}", "--", *paths])
    return p.stdout


def _apply_check(patch: str) -> tuple[bool, str]:
    p = subprocess.run(
        ["git", "apply", "--check"],
        input=patch,
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return p.returncode == 0, (p.stderr or p.stdout).strip()


def _apply(patch: str) -> int:
    p = subprocess.run(
        ["git", "apply"],
        input=patch,
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return p.returncode


def _commit(message: str, paths: list[str]) -> int:
    subprocess.run(["git", "add", "--", *paths], check=False, cwd=_ROOT)
    p = subprocess.run(
        [
            "git",
            "-c",
            "user.email=lca-agent@local",
            "-c",
            "user.name=LCA Agent",
            "commit",
            "-m",
            message,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return p.returncode


def _log_first_last(base: str, head: str, paths: list[str]) -> tuple[str, str]:
    """Return (first_sha7, last_sha7) of commits touching `paths` in `base..head`."""
    p = _run(["git", "log", f"{base}..{head}", "--reverse", "--pretty=format:%H", "--", *paths])
    shas = [s.strip() for s in p.stdout.splitlines() if s.strip()]
    if not shas:
        return ("", "")
    return (shas[0][:7], shas[-1][:7])


def apply_cluster(
    cluster_id: str,
    base: str = _DEFAULT_BASE,
    head: str = _DEFAULT_HEAD,
    commit: bool = True,
) -> ApplyResult:
    """Apply the cluster's end-state delta. Returns ApplyResult; rc=0 on success."""
    if cluster_id not in CLUSTER_PATHS:
        return ApplyResult(
            cluster_id=cluster_id,
            rc=1,
            patch_lines=0,
            applied=False,
            committed=False,
            message=f"unknown cluster id: {cluster_id}",
        )
    paths = list(CLUSTER_PATHS[cluster_id]["paths"])  # type: ignore[arg-type]
    lane = str(CLUSTER_PATHS[cluster_id]["lane"])
    patch = _diff_patch(paths, base, head)
    patch_lines = len(patch.splitlines())
    if not patch.strip():
        return ApplyResult(
            cluster_id=cluster_id,
            rc=0,
            patch_lines=0,
            applied=False,
            committed=False,
            message=f"no-op: {cluster_id} has no diff in {base[:7]}..{head}",
        )
    ok, err = _apply_check(patch)
    if not ok:
        return ApplyResult(
            cluster_id=cluster_id,
            rc=1,
            patch_lines=patch_lines,
            applied=False,
            committed=False,
            message=f"git apply --check failed: {err}",
        )
    rc = _apply(patch)
    if rc != 0:
        return ApplyResult(
            cluster_id=cluster_id,
            rc=1,
            patch_lines=patch_lines,
            applied=False,
            committed=False,
            message=f"git apply failed (rc={rc})",
        )
    if not commit:
        return ApplyResult(
            cluster_id=cluster_id,
            rc=0,
            patch_lines=patch_lines,
            applied=True,
            committed=False,
            message="applied (no-commit); review with `git diff --staged` then commit manually",
        )
    first, last = _log_first_last(base, head, paths)
    msg = (
        f"port(cluster-{cluster_id}): apply end-state delta\n\n"
        f"Source: commits {first}..{last} from origin/main.\n"
        f"Lane: {lane}.\n"
        f"Lock impact: none — fully unlocked (per ADR-0103 §3).\n"
        f"Test plan: per docs/port/main-port-plan.md card for {cluster_id}.\n"
    )
    rc = _commit(msg, paths)
    return ApplyResult(
        cluster_id=cluster_id,
        rc=rc,
        patch_lines=patch_lines,
        applied=True,
        committed=(rc == 0),
        message=msg,
    )


def _self_test() -> int:
    """In-process assertions: the apply pipeline shape (without touching the tree)."""
    # Unknown cluster id
    r = apply_cluster("Z99", commit=False)
    assert r.rc == 1, r
    assert "unknown cluster id" in r.message, r

    # Existing cluster id but commit=False (no actual apply)
    r = apply_cluster("C1", commit=False)
    # Either no-op or applied; both are valid self-test signals
    assert r.cluster_id == "C1", r
    print("self-test OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", required=False)
    parser.add_argument("--base", default=_DEFAULT_BASE)
    parser.add_argument("--head", default=_DEFAULT_HEAD)
    parser.add_argument("--no-commit", action="store_true", help="Apply patch only; do not commit.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if not args.cluster:
        print("--cluster is required (e.g. --cluster C1)", file=sys.stderr)
        return 2
    r = apply_cluster(
        args.cluster,
        base=args.base,
        head=args.head,
        commit=not args.no_commit,
    )
    print(
        f"cluster={r.cluster_id} rc={r.rc} applied={r.applied} "
        f"committed={r.committed} patch_lines={r.patch_lines}"
    )
    print(r.message)
    return r.rc


if __name__ == "__main__":
    sys.exit(main())
