#!/usr/bin/env python3
"""Render per-cluster end-state cards for main-port-plan.md.

For each cluster (C1..C47 + locked), runs `git log <base>..<head> --oneline -- <paths>`
to count commits, `git diff --name-only <base>..<head> -- <paths>` to list
top changed files, and emits a markdown card per ADR-0103 schema.

CLI:
    --cluster <id>    render only this cluster
    --base <ref>      base commit (default: $MERGE_BASE)
    --head <ref>      head commit (default: origin/main)
    --output <path>   output file (default: docs/port/main-port-plan.md)
    --self-test       run in-process assertions

Library:
    render_card(...) -> str
    CLUSTER_PATHS: dict[cluster_id, dict[paths, lane]]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_BASE = "bae32d8c27ee2b59312303fbfa68d4738c2f316f"
_DEFAULT_HEAD = "origin/main"
_DEFAULT_OUTPUT = "docs/port/main-port-plan.md"


# Cluster → {paths: list[str], lane: str}. Each path list is the union of
# "main has touched these in this cluster since merge-base".
CLUSTER_PATHS: dict[str, dict[str, object]] = {
    "C1": {"paths": ["lca/contracts/atoms/"], "lane": "A"},
    "C2": {"paths": ["lca/contracts/mechanisms/"], "lane": "A"},
    "C3": {"paths": ["lca/contracts/models/"], "lane": "A"},
    "C4": {"paths": ["lca/contracts/protocols/"], "lane": "A"},
    "C5": {"paths": ["lca/contracts/harness/"], "lane": "A"},
    "C6": {"paths": ["lca/contracts/capabilities.py"], "lane": "A"},
    "C7": {"paths": ["docs/adr/"], "lane": "A"},
    "C8": {"paths": ["docs/specs/", "docs/design/"], "lane": "A"},
    "C9": {
        "paths": ["lca/harness/profile/", "lca/harness/boot.py", "lca/harness/resolve.py"],
        "lane": "A",
    },
    "C10": {"paths": ["lca/harness/session/", "lca/harness/agent/"], "lane": "A"},
    "C11": {"paths": ["lca/harness/middleware/"], "lane": "A"},
    "C12": {"paths": ["lca/harness/plugin_api.py"], "lane": "A"},
    "C13": {"paths": ["lca/harness/skills/", "lca/harness/workflow/"], "lane": "A"},
    "C14": {"paths": ["lca/harness/diagnostics/"], "lane": "A"},
    "C15": {"paths": ["lca/layer0_infra/llm/"], "lane": "B"},
    "C16": {"paths": ["lca/layer0_infra/tools/"], "lane": "B"},
    "C17": {"paths": ["lca/layer0_infra/transport/"], "lane": "B"},
    "C18": {"paths": ["lca/layer0_infra/sandbox/"], "lane": "B"},
    "C19": {"paths": ["lca/layer0_infra/observability/"], "lane": "B"},
    "C20": {"paths": ["lca/layer0_infra/dsh/"], "lane": "B"},
    "C21": {"paths": ["lca/layer0_infra/plane/"], "lane": "B"},
    "C22": {"paths": ["lca/layer1_cognitive/brain/"], "lane": "B"},
    "C23": {"paths": ["lca/layer1_cognitive/body/"], "lane": "B"},
    "C24": {
        "paths": ["lca/layer1_cognitive/perceive_hub.py", "lca/layer1_cognitive/perceive_sink.py"],
        "lane": "B",
    },
    "C25": {"paths": ["lca/layer1_cognitive/sensors/"], "lane": "B"},
    "C26": {
        "paths": [
            "lca/layer1_cognitive/collaboration/",
            "lca/layer1_cognitive/event_bus.py",
            "lca/layer1_cognitive/hook_registry.py",
        ],
        "lane": "B",
    },
    "C27": {
        "paths": ["lca/layer1_cognitive/memory/", "lca/layer1_cognitive/member_status/"],
        "lane": "B",
    },
    "C28": {"paths": ["lca/layer2_runtime/"], "lane": "B"},
    "C29": {"paths": ["lca/plugins/guards/"], "lane": "B"},
    "C30": {"paths": ["lca/layer3_agent/"], "lane": "B"},
    "C31": {"paths": ["lca/layer4_app/"], "lane": "B"},
    "C32": {"paths": ["lca/plugins/seam_definitions/"], "lane": "B"},
    "C33": {"paths": ["lca/plugins/providers/"], "lane": "B"},
    "C34": {
        "paths": [
            "lca/plugins/brain/",
            "lca/plugins/reasoner/",
            "lca/plugins/synthesizer/",
            "lca/plugins/loop_cognitive/",
            "lca/plugins/team_lead/",
        ],
        "lane": "B",
    },
    "C35": {"paths": ["lca/plugins/dsh/"], "lane": "B"},
    "C36": {"paths": ["gateway/runs/api.py"], "lane": "C"},
    "C37": {"paths": ["gateway/runs/execute.py"], "lane": "C"},
    "C38": {"paths": ["gateway/runs/openai_shim.py"], "lane": "C"},
    "C39": {"paths": ["gateway/runs/loop_drivers.py"], "lane": "C"},
    "C40": {"paths": ["gateway/app.py"], "lane": "C"},
    "C41": {"paths": ["profiles/"], "lane": "B"},
    "C42": {"paths": ["bundles/"], "lane": "B"},
    "C43": {"paths": ["scripts/"], "lane": "B"},
    "C44": {"paths": ["tests/"], "lane": "A"},  # tests for A-lane areas
    "C45": {"paths": ["tests/"], "lane": "B"},  # tests for B-lane areas
    "C46": {"paths": ["tests/"], "lane": "B"},  # tests for plugins
    "C47": {"paths": ["tests/"], "lane": "C"},  # tests for gateway
}


def _git_log_count(base: str, head: str, paths: list[str]) -> int:
    p = subprocess.run(
        ["git", "log", f"{base}..{head}", "--oneline", "--", *paths],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return len([line for line in p.stdout.splitlines() if line])


def _git_diff_files(base: str, head: str, paths: list[str], limit: int = 5) -> list[str]:
    p = subprocess.run(
        ["git", "diff", f"{base}..{head}", "--name-only", "--", *paths],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return [line.strip() for line in p.stdout.splitlines() if line.strip()][:limit]


def _git_log_subject(ref: str) -> str:
    p = subprocess.run(
        ["git", "log", "-1", ref, "--format=%H%n%s"],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return p.stdout.strip()


def _lock_impact(cluster_id: str, paths: list[str]) -> str:
    """Return the lock-impact line per ADR-0103 §3 rules."""
    soft = {
        "C36": "gateway/runs/api.py",
        "C37": "gateway/runs/execute.py",
        "C38": "gateway/runs/openai_shim.py",
        "C39": "gateway/runs/loop_drivers.py",
        "C40": "gateway/app.py",
    }
    if cluster_id in soft:
        return f"soft:{soft[cluster_id]} — wire-shape preserved by gate"
    return "none — fully unlocked"


def _recommendation(cluster_id: str, lane: str) -> str:
    if lane == "A":
        return "port as-is"
    if lane == "B":
        return "investigate: confirm lane A criteria do not apply"
    return "skip (Lane C: soft-lock / chore / cleanup)"


def _test_plan(cluster_id: str, files: list[str]) -> str:
    test_files = [f for f in files if f.startswith("tests/")]
    if test_files:
        return ", ".join(test_files)
    return "no test path auto-detected; recommend manual review"


def render_card(
    cluster_id: str,
    paths: list[str],
    lane: str,
    commit_count: int,
    main_tip_sha: str,
    main_tip_subject: str,
    branch_sha: str,
    branch_subject: str,
    key_symbols: list[str],
) -> str:
    lock = _lock_impact(cluster_id, paths)
    rec = _recommendation(cluster_id, lane)
    test_plan = _test_plan(cluster_id, key_symbols)
    symbols_str = ", ".join(f"`{s}`" for s in key_symbols) if key_symbols else "(none)"
    delta = (
        f"{commit_count} commits touch {', '.join(f'`{p}`' for p in paths)}; "
        f"see `git diff {_DEFAULT_BASE[:7]}..{_DEFAULT_HEAD.split('/')[-1]} "
        f"-- {' '.join(paths)}` for the full delta."
    )
    return f"""### {cluster_id}: {cluster_id} cluster

- **Lane**: {lane}
- **Path(s)**: {", ".join(f"`{p}`" for p in paths)}
- **Main commits touching this cluster**: {commit_count} (range {_DEFAULT_BASE[:7]}..{_DEFAULT_HEAD.split("/")[-1]})
- **Branch HEAD**: `{branch_sha[:7]}` — {branch_subject}
- **Main tip**: `{main_tip_sha[:7]}` — {main_tip_subject}
- **End-state delta**: {delta}
- **Key symbols touched**: {symbols_str}
- **Lock impact**: {lock}
- **Default recommendation**: {rec}
- **Test plan**: {test_plan}
- **DAG deps**: (none)
- **Mark**: [ ] port  [ ] skip  [ ] hold  [ ] investigate
"""


def render_one(cluster_id: str, base: str, head: str) -> str:
    info = CLUSTER_PATHS[cluster_id]
    paths = info["paths"]  # type: ignore[assignment]
    lane = info["lane"]  # type: ignore[assignment]
    n = _git_log_count(base, head, paths)  # type: ignore[arg-type]
    files = _git_diff_files(base, head, paths)  # type: ignore[arg-type]
    tip = _git_log_subject(head).splitlines()
    branch = _git_log_subject("HEAD").splitlines()
    main_tip_sha = tip[0] if tip else "HEAD"
    main_tip_subject = tip[1] if len(tip) > 1 else ""
    branch_sha = branch[0] if branch else "HEAD"
    branch_subject = branch[1] if len(branch) > 1 else ""
    return render_card(
        cluster_id=cluster_id,
        paths=paths,  # type: ignore[arg-type]
        lane=lane,  # type: ignore[arg-type]
        commit_count=n,
        main_tip_sha=main_tip_sha,
        main_tip_subject=main_tip_subject,
        branch_sha=branch_sha,
        branch_subject=branch_subject,
        key_symbols=files,
    )


def render_all(base: str, head: str) -> str:
    tip = _git_log_subject(head).splitlines()
    main_tip = tip[0] if tip else head
    main_tip_subj = tip[1] if len(tip) > 1 else ""
    parts = [
        "# main-port-plan\n",
        f"Auto-generated by `scripts/port_endstate.py` against `{_DEFAULT_BASE[:7]}..{_DEFAULT_HEAD}`.\n\n",
        f"Main tip: `{main_tip[:7]}` — {main_tip_subj}\n\n",
        "## Summary\n\n",
        "- Total main commits since merge-base: see [`main-classification.md`](main-classification.md)\n",
        "- Cluster count: 47 (C1..C47, all listed below)\n",
        "- Lane A (default port): see ADR-0103 §3\n",
        "- Lane B (investigate): see ADR-0103 §3\n",
        "- Lane C (skip): see ADR-0103 §3\n\n",
        "## Cards\n",
    ]
    for cid in sorted(CLUSTER_PATHS.keys()):
        parts.append(render_one(cid, base, head))
    return "".join(parts)


def _self_test() -> int:
    """In-process assertions: card schema + cluster coverage."""
    info = CLUSTER_PATHS["C16"]
    card = render_card(
        cluster_id="C16",
        paths=info["paths"],  # type: ignore[arg-type]
        lane=info["lane"],  # type: ignore[arg-type]
        commit_count=12,
        main_tip_sha="0dc34a1e",
        main_tip_subject="feat(tools): flatten tool observation payload",
        branch_sha="5204fd56",
        branch_subject="fix(gateway): restore LobeHub SSE",
        key_symbols=["lca/layer0_infra/tools/render_contract.py"],
    )
    assert "### C16" in card
    assert "**Lane**: B" in card
    assert "Main commits touching this cluster**: 12" in card
    assert "**Mark**: [ ] port" in card
    # C16 is Layer 0 tools — fully unlocked
    assert "**Lock impact**: none" in card

    # C36 (gateway) is soft-lock
    info = CLUSTER_PATHS["C36"]
    card = render_card(
        cluster_id="C36",
        paths=info["paths"],  # type: ignore[arg-type]
        lane=info["lane"],  # type: ignore[arg-type]
        commit_count=4,
        main_tip_sha="0dc34a1e",
        main_tip_subject="x",
        branch_sha="5204fd56",
        branch_subject="y",
        key_symbols=[],
    )
    assert "soft:gateway/runs/api.py" in card
    assert "Lane**: C" in card

    # Cluster coverage
    expected = {f"C{i}" for i in range(1, 48)}
    assert expected.issubset(CLUSTER_PATHS.keys()), (
        f"missing: {sorted(expected - CLUSTER_PATHS.keys())}"
    )

    print(f"self-test OK: {len(CLUSTER_PATHS)} cluster cards")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster", help="Render only this cluster id (e.g. C16)")
    parser.add_argument("--base", default=_DEFAULT_BASE)
    parser.add_argument("--head", default=_DEFAULT_HEAD)
    parser.add_argument("--output", default=_DEFAULT_OUTPUT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if args.cluster:
        content = render_one(args.cluster, args.base, args.head)
    else:
        content = render_all(args.base, args.head)
    out = _ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
