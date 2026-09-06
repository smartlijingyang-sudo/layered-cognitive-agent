#!/usr/bin/env python3
"""Bulk-rewrite import paths after cognitive directory reorganization.

Usage:
    uv run python scripts/migrate_import_paths.py --dry-run
    uv run python scripts/migrate_import_paths.py --apply
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"__pycache__", ".git", ".venv", "vendor", "lobehub-ui", "node_modules"}

# old_module -> new_module (longest match first when sorting)
IMPORT_REWRITES: dict[str, str] = {
    "lca.harness.plugin.spec_projection": "lca.harness.plugin.spec_projection",
    "lca.harness.plugin.declaration": "lca.harness.plugin.declaration",
    "lca.harness.plugin.context": "lca.harness.plugin.context",
    "lca.harness.plugin.manifest": "lca.harness.plugin.manifest",
    "lca.harness.continuous.serialization": "lca.harness.continuous.serialization",
    "lca.harness.continuous.queue": "lca.harness.continuous.queue",
    "lca.harness.continuous.session": "lca.harness.continuous.session",
    "lca.cognition.wire.registry_factory": "lca.cognition.wire.registry_factory",
    "lca.cognition.wire.envelope": "lca.cognition.wire.envelope",
    "lca.cognition.perceive.service": "lca.cognition.perceive.service",
    "lca.cognition.perceive.hub": "lca.cognition.perceive.hub",
    "lca.cognition.collaboration.group_assembly": "lca.cognition.collaboration.group_assembly",
    "lca.cognition.brain.gate.hook_registry": "lca.cognition.brain.gate.hook_registry",
    "lca.cognition.brain.gate.gate_service": "lca.cognition.brain.gate.gate_service",
    "lca.loop.commit.delegation_journal": "lca.loop.commit.delegation_journal",
    "lca.loop.commit.phase_spine": "lca.loop.commit.phase_spine",
    "lca.loop.commit.memory_journal": "lca.loop.commit.memory_journal",
    "lca.loop.commit.act_journal": "lca.loop.commit.act_journal",
    "lca.loop.commit.tool_journal": "lca.loop.commit.tool_journal",
    "lca.loop.emit.spine.phase_fact": "lca.loop.emit.spine.phase_fact",
    "lca.loop.emit.spine.kernel_loop": "lca.loop.emit.spine.kernel_loop",
    "lca.loop.emit.cognitive.agent_spawn": "lca.loop.emit.cognitive.agent_spawn",
    "lca.loop.emit.cognitive.reasoner": "lca.loop.emit.cognitive.reasoner",
    "lca.loop.emit.spine.ep": "lca.loop.emit.spine.ep",
    "lca.loop.transport": "lca.loop.transport",
    "lca.loop.emit.cognitive.llm": "lca.loop.emit.cognitive.llm",
    "lca.session.lifecycle.checkpoint": "lca.session.lifecycle.checkpoint",
    "lca.session.lifecycle.recovery": "lca.session.lifecycle.recovery",
    "lca.session.lifecycle.repair": "lca.session.lifecycle.repair",
    "lca.session.lifecycle.bind": "lca.session.lifecycle.bind",
}

SORTED_OLD = sorted(IMPORT_REWRITES, key=len, reverse=True)


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for base in (ROOT / "lca", ROOT / "lca_kernel", ROOT / "tests", ROOT / "scripts", ROOT / "docs"):
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if any(p in SKIP for p in path.parts):
                continue
            files.append(path)
    return files


def rewrite_content(text: str) -> tuple[str, int]:
    changes = 0
    for old in SORTED_OLD:
        new = IMPORT_REWRITES[old]
        # from X import / from X import Y / import X
        patterns = [
            (rf"\bfrom {re.escape(old)} import\b", f"from {new} import"),
            (rf"\bimport {re.escape(old)}\b", f"import {new}"),
            (rf'"{re.escape(old)}"', f'"{new}"'),
            (rf"'{re.escape(old)}'", f"'{new}'"),
        ]
        for pat, repl in patterns:
            new_text, n = re.subn(pat, repl, text)
            if n:
                text = new_text
                changes += n
    return text, changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes")
    args = parser.parse_args()
    apply = args.apply

    total_files = 0
    total_changes = 0
    for path in _iter_py_files():
        original = path.read_text(encoding="utf-8")
        updated, n = rewrite_content(original)
        if n:
            total_files += 1
            total_changes += n
            rel = path.relative_to(ROOT)
            print(f"  {rel}: {n} rewrite(s)")
            if apply:
                path.write_text(updated, encoding="utf-8")

    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"\n{mode}: {total_changes} rewrite(s) in {total_files} file(s)")
    if not apply:
        print("Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
