"""Verify docs/debug/run-debug-guide.md command references match the CLI SSOT.

The CLI's command registry is the single source of truth — this script
asks the CLI itself what commands it serves (`lca-ops --help` plus
`lca-ops <group> --help`) and validates every `lca-ops ...` path the
SOP mentions.

This is a sync gate: if the CLI evolves but the SOP doesn't, CI catches
it here. The SOP is meant for coding agents and they will silently
assume commands that don't exist are real.

The check is one-directional: new CLI commands are not failures (they
appear in `lca-ops --help` and the agent can use them); only SOP mentions
of commands that no longer exist are errors. This matches "the SOP must
not lie", not "the SOP must be exhaustive".

Exit codes:
    0  SOP ↔ CLI in sync
    1  SOP references commands that no longer exist
    2  internal error (could not invoke CLI)

Run:
    uv run python scripts/check_run_debug_sync.py
    uv run python scripts/check_run_debug_sync.py --verbose
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOP = REPO / "docs" / "debug" / "run-debug-guide.md"
LCA_OPS = REPO / "scripts" / "lca-ops"

# SOP command-path capture: `lca-ops foo bar`
SOP_CMD_RE = re.compile(r"`lca-ops((?:\s+[a-z][a-z0-9-]+)+)`")

# typer `Commands:` block: each line `  <name>   <desc>` (2-space indent).
CMD_LINE_RE = re.compile(r"^\s{2}([a-z][a-z0-9-]+)\s{2,}\S")


def _run(args: list[str], timeout: float = 15.0) -> str:
    """Run lca-ops with given args; return stdout."""
    cp = subprocess.run(  # noqa: S603 — invoker is this repo's CLI, not untrusted
        [str(LCA_OPS), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO),
    )
    return cp.stdout + cp.stderr


def _parse_commands_block(help_text: str) -> list[str]:
    """Extract command names from typer's ``Commands:`` section."""
    out: list[str] = []
    in_cmds = False
    for line in help_text.splitlines():
        if line.strip() == "Commands:":
            in_cmds = True
            continue
        if in_cmds:
            if not line.strip():
                # Blank line ends the block.
                if out:
                    break
                continue
            m = CMD_LINE_RE.match(line)
            if m:
                out.append(m.group(1))
            elif line.startswith("Options:") or line.startswith("─"):
                # Sub-section markers; ignore.
                continue
    return out


def parse_cli() -> tuple[set[str], dict[str, set[str]]]:
    """Return (top-level commands, {group_name: children}).

    Sources, in order:
      1. `lca-ops --help` → top-level commands and group names (mix).
      2. For each candidate group, `lca-ops <group> --help` → its children.
      3. For each candidate top-level command, `lca-ops <cmd> --help` to
         confirm it is not itself a group with its own children.
    """
    help_text = _run(["--help"])
    candidates = _parse_commands_block(help_text)

    top: set[str] = set()
    groups: dict[str, set[str]] = {}

    for name in candidates:
        sub_help = _run([name, "--help"])
        sub_cmds = _parse_commands_block(sub_help)
        if sub_cmds:
            # It's a Typer sub-app (group).
            groups[name] = set(sub_cmds)
        else:
            top.add(name)

    return top, groups


def parse_sop() -> list[tuple[str, tuple[str, ...]]]:
    """Yield (raw_match, tuple_of_segments) for every `lca-ops ...` path."""
    text = SOP.read_text(encoding="utf-8")
    out: list[tuple[str, tuple[str, ...]]] = []
    for m in SOP_CMD_RE.finditer(text):
        out.append((m.group(0), tuple(m.group(1).split())))
    return out


def validate(
    sop_paths: list[tuple[str, tuple[str, ...]]],
    top: set[str],
    groups: dict[str, set[str]],
) -> list[str]:
    """Return error messages; empty list = in sync."""
    errors: list[str] = []
    seen: set[tuple[str, ...]] = set()

    for raw, path in sop_paths:
        if path in seen:
            continue
        seen.add(path)
        first, rest = path[0], path[1:]

        if first in groups:
            if rest:
                child = rest[0]
                if child not in groups[first] and child not in top:
                    errors.append(
                        f"{raw!r} → group '{first}' has no child '{child}' "
                        f"(children: {sorted(groups[first])})"
                    )
            continue
        if first in top:
            continue
        errors.append(
            f"{raw!r} → '{first}' is not a registered command or group. "
            f"Run `./scripts/lca-ops --help` to see what is."
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if not SOP.exists():
        print(f"ERROR: SOP not found at {SOP}", file=sys.stderr)
        return 2
    if not LCA_OPS.exists():
        print(f"ERROR: lca-ops not found at {LCA_OPS}", file=sys.stderr)
        return 2

    try:
        top, groups = parse_cli()
    except subprocess.TimeoutExpired:
        print("ERROR: lca-ops --help timed out", file=sys.stderr)
        return 2

    sop_paths = parse_sop()
    errors = validate(sop_paths, top, groups)

    if args.verbose:
        print(f"SOP paths parsed: {len(sop_paths)}")
        print(f"Top-level commands ({len(top)}): {sorted(top)}")
        print(f"Groups ({len(groups)}):")
        for g, kids in sorted(groups.items()):
            print(f"  - {g}: {sorted(kids)}")
        print()

    if errors:
        print(f"SOP ↔ CLI OUT OF SYNC ({len(errors)} issue(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Fix: remove the SOP reference, or rename the command and update "
            "the SOP in the same change. New CLI commands are fine (they "
            "appear in `./scripts/lca-ops --help`).",
            file=sys.stderr,
        )
        return 1

    print(
        f"SOP ↔ CLI in sync "
        f"({len(sop_paths)} SOP paths, "
        f"{len(top)} top-level commands, {len(groups)} groups)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
