#!/usr/bin/env python3
"""Classify main commits since merge-base into 47 clusters + A/B/C lanes.

Reads `git log <base>..<head>` and `git diff-tree` for each commit's
files, applies a deterministic path-prefix → cluster-id mapping, and
emits a markdown table suitable for human triage.

Lane rules (per ADR-0103 §3):
- A (port): lca/contracts/*, lca/harness/*, docs/{adr,specs,design}/*, tests matching those
- B (investigate): lca/layer{0,1,2,3,4}/*, lca/plugins/*, gateway/runs/* (soft-locked),
  profiles/*, bundles/*, scripts/*
- C (skip): deploy/lobehub/* (hard-lock), fix(lobehub*) / feat(lobehub-patches*),
  chore/cleanup/format, DSH-only, YAGNI cleanup unless the alias exists here.

CLI:
    --base <ref>     base commit (default: $MERGE_BASE)
    --head <ref>     head commit (default: origin/main)
    --output <path>  output file (default: docs/port/main-classification.md)
    --self-test      run in-process assertions

Library:
    classify_commit(sha, subject, files) -> Classification
    CLUSTER_MAP: ordered list[(prefix, cluster_id, lane)]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_BASE = "bae32d8c27ee2b59312303fbfa68d4738c2f316f"  # pragma: allowlist secret  # git merge-base SHA, not a credential
_DEFAULT_HEAD = "origin/main"
_DEFAULT_OUTPUT = "docs/port/main-classification.md"


@dataclass(frozen=True)
class Classification:
    sha: str
    subject: str
    cluster: str
    lane: str
    notes: str


# 47-cluster map. Order matters: first match wins.
# Lane "C" for hard-locked paths.
CLUSTER_MAP: list[tuple[str, str, str]] = [
    # Hard-lock
    ("deploy/lobehub/", "locked", "C"),
    # Contracts (Lane A)
    ("lca/contracts/atoms/", "C1", "A"),
    ("lca/contracts/mechanisms/", "C2", "A"),
    ("lca/contracts/models/", "C3", "A"),
    ("lca/contracts/protocols/", "C4", "A"),
    ("lca/contracts/harness/", "C5", "A"),
    ("lca/contracts/capabilities.py", "C6", "A"),
    # Docs (Lane A)
    ("docs/adr/", "C7", "A"),
    ("docs/specs/", "C8", "A"),
    ("docs/design/", "C8", "A"),
    # Harness (Lane A)
    ("lca/harness/profile/", "C9", "A"),
    ("lca/harness/boot.py", "C9", "A"),
    ("lca/harness/resolve.py", "C9", "A"),
    ("lca/harness/session/", "C10", "A"),
    ("lca/harness/agent/", "C10", "A"),
    ("lca/harness/middleware/", "C11", "A"),
    ("lca/harness/plugin_api.py", "C12", "A"),
    ("lca/harness/skills/", "C13", "A"),
    ("lca/harness/workflow/", "C13", "A"),
    ("lca/harness/diagnostics/", "C14", "A"),
    # Layer 0 (Lane B)
    ("lca/layer0_infra/llm/", "C15", "B"),
    ("lca/layer0_infra/tools/", "C16", "B"),
    ("lca/layer0_infra/transport/", "C17", "B"),
    ("lca/layer0_infra/sandbox/", "C18", "B"),
    ("lca/layer0_infra/observability/", "C19", "B"),
    ("lca/layer0_infra/dsh/", "C20", "B"),
    ("lca/layer0_infra/plane/", "C21", "B"),
    # Layer 1 (Lane B)
    ("lca/layer1_cognitive/brain/", "C22", "B"),
    ("lca/layer1_cognitive/body/", "C23", "B"),
    ("lca/layer1_cognitive/perceive_hub.py", "C24", "B"),
    ("lca/layer1_cognitive/perceive_sink.py", "C24", "B"),
    ("lca/layer1_cognitive/sensors/", "C25", "B"),
    ("lca/layer1_cognitive/collaboration/", "C26", "B"),
    ("lca/layer1_cognitive/event_bus.py", "C26", "B"),
    ("lca/layer1_cognitive/hook_registry.py", "C26", "B"),
    ("lca/layer1_cognitive/memory/", "C27", "B"),
    ("lca/layer1_cognitive/member_status/", "C27", "B"),
    # Layer 2 (Lane B)
    ("lca/layer2_runtime/", "C28", "B"),
    ("lca/plugins/guards/", "C29", "B"),
    # Layer 3 (Lane B)
    ("lca/layer3_agent/", "C30", "B"),
    # Layer 4 (Lane B)
    ("lca/layer4_app/", "C31", "B"),
    # Plugins (Lane B)
    ("lca/plugins/seam_definitions/", "C32", "B"),
    ("lca/plugins/providers/", "C33", "B"),
    ("lca/plugins/brain/", "C34", "B"),
    ("lca/plugins/reasoner/", "C34", "B"),
    ("lca/plugins/synthesizer/", "C34", "B"),
    ("lca/plugins/loop_cognitive/", "C34", "B"),
    ("lca/plugins/team_lead/", "C34", "B"),
    ("lca/plugins/dsh/", "C35", "B"),
    # Gateway (Lane C — soft-lock)
    ("gateway/runs/api.py", "C36", "C"),
    ("gateway/runs/execute.py", "C37", "C"),
    ("gateway/runs/openai_shim.py", "C38", "C"),
    ("gateway/runs/loop_drivers.py", "C39", "C"),
    ("gateway/app.py", "C40", "C"),
    # Profiles / Bundles / Scripts (Lane B)
    ("profiles/", "C41", "B"),
    ("bundles/", "C42", "B"),
    ("scripts/", "C43", "B"),
]


def classify_commit(sha: str, subject: str, files: list[str]) -> Classification:
    """Classify a single commit into (cluster, lane, notes)."""
    # Hard-lock paths always win
    for f in files:
        if f.startswith("deploy/lobehub/"):
            return Classification(sha, subject, "locked", "C", f"hard-lock: {f}")
    # Chore / cleanup / format
    for prefix in ("chore:", "style:", "docs:"):
        if subject.startswith(prefix):
            return Classification(sha, subject, "skip-chore", "C", prefix.rstrip(":"))
    # DSH-only commit (subject references dsh and only touches dsh-related paths)
    if "dsh" in subject.lower() and all(
        "dsh" in f.lower() or f.startswith("scripts/") for f in files
    ):
        return Classification(sha, subject, "skip-dsh", "C", "DSH-only")
    # YAGNI cleanup — refactor + remove/kill/delete
    if subject.startswith("refactor:") and any(
        kw in subject.lower() for kw in ("remove", "kill", "delete", "drop")
    ):
        return Classification(sha, subject, "skip-yagni", "C", "YAGNI cleanup")
    # Tests for A-lane areas — promote to C44
    if files and files[0].startswith("tests/"):
        return Classification(sha, subject, "C45", "B", f"tests: {files[0]}")
    # First-match path cluster
    for f in files:
        for prefix, cluster, lane in CLUSTER_MAP:
            if f.startswith(prefix):
                return Classification(sha, subject, cluster, lane, f"touches {prefix}")
    # Keyword fallback (no path match)
    subj = subject.lower()
    if "adr" in subj:
        return Classification(sha, subject, "C7", "A", "adr-keyword")
    if "harness" in subj:
        return Classification(sha, subject, "C9", "A", "harness-keyword")
    return Classification(sha, subject, "unclassified", "B", "needs manual review")


def _git_log(base: str, head: str) -> list[tuple[str, str]]:
    """Yield (sha, subject) tuples for `base..head`."""
    fmt = "%H%x00%s"
    p = subprocess.run(
        ["git", "log", f"{base}..{head}", f"--pretty=format:{fmt}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    rows: list[tuple[str, str]] = []
    for line in p.stdout.splitlines():
        if not line:
            continue
        sha, subject = line.split("\x00", 1)
        rows.append((sha, subject))
    return rows


def _git_files(sha: str) -> list[str]:
    p = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return [line.strip() for line in p.stdout.splitlines() if line.strip()]


def render_markdown(rows: list[Classification]) -> str:
    """Render the classification table as markdown."""
    lines = [
        "# main-classification",
        "",
        f"Auto-generated by `scripts/port_classify.py` against "
        f"`{_DEFAULT_BASE[:7]}..{_DEFAULT_HEAD}`. Re-run the script to refresh.",
        "",
        "| sha | subject | cluster | lane | notes |",
        "|-----|---------|---------|------|-------|",
    ]
    for r in rows:
        sha_short = r.sha[:7]
        subject = r.subject.replace("|", "\\|")
        notes = r.notes.replace("|", "\\|")
        lines.append(f"| {sha_short} | {subject} | {r.cluster} | {r.lane} | {notes} |")
    lines.append("")
    return "\n".join(lines)


def _self_test() -> int:
    """In-process assertions: classifier handles each lane correctly."""
    # Hard-lock
    c = classify_commit(
        "0" * 40,
        "fix(lobehub-patches): preserve streaming output",
        ["deploy/lobehub/patches/runtime/LcaRunDriver.ts"],
    )
    assert c.cluster == "locked" and c.lane == "C", c

    # ADR (Lane A)
    c = classify_commit(
        "1" * 40,
        "docs(adr-0101): Tool events evidence flow",
        ["docs/adr/0101-tool-events.md"],
    )
    assert c.cluster == "C7" and c.lane == "A", c

    # Harness profile (Lane A)
    c = classify_commit(
        "2" * 40,
        "feat(harness): boot_resolved_profile()",
        ["lca/harness/profile/boot.py"],
    )
    assert c.cluster == "C9" and c.lane == "A", c

    # Layer 1 brain (Lane B)
    c = classify_commit(
        "3" * 40,
        "feat(brain): improve Reasoner heuristic",
        ["lca/layer1_cognitive/brain/reasoner.py"],
    )
    assert c.cluster == "C22" and c.lane == "B", c

    # Gateway api.py (Lane C — soft-lock)
    c = classify_commit(
        "4" * 40,
        "feat(gateway): add /runs/stream endpoint",
        ["gateway/runs/api.py"],
    )
    assert c.cluster == "C36" and c.lane == "C", c

    # Chore (Lane C skip)
    c = classify_commit(
        "5" * 40,
        "chore: format foo.py",
        ["lca/foo.py"],
    )
    assert c.cluster == "skip-chore" and c.lane == "C", c

    # Tests default to C45 (Lane B)
    c = classify_commit(
        "6" * 40,
        "test: cover new evidence path",
        ["tests/test_evidence.py"],
    )
    assert c.cluster == "C45" and c.lane == "B", c

    # Cluster map length check
    assert len(CLUSTER_MAP) >= 47, f"CLUSTER_MAP has only {len(CLUSTER_MAP)} entries"

    print(f"self-test OK: {len(CLUSTER_MAP)} cluster entries")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=_DEFAULT_BASE)
    parser.add_argument("--head", default=_DEFAULT_HEAD)
    parser.add_argument("--output", default=_DEFAULT_OUTPUT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    rows = [
        classify_commit(sha, subject, _git_files(sha))
        for sha, subject in _git_log(args.base, args.head)
    ]
    md = render_markdown(rows)
    out = _ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
