#!/usr/bin/env python3
r"""Pre-commit guard: enforce ADR-0103 hard-lock + soft-lock surface.

Parses the hard-lock and soft-lock path tables from
`docs/adr/0103-locked-surface-and-port-policy.md` (regex over `` `- `path`` ``
list items under the `### 1. Hard-lock` and `### 2. Soft-lock`
sub-sections) and checks `git diff <base>..HEAD --name-only` for any
non-whitespace change to those paths.

Exit codes:
- 0: clean (or only soft-lock warnings).
- 1: at least one hard-lock violation.

CLI:
    --base <ref>     Diff base (default: HEAD).
    --adr <path>     ADR file (default: docs/adr/0103-locked-surface-and-port-policy.md).
    --fake-diff <p>  Inject a synthetic changed path (for tests; may repeat).
    --self-test      Run in-process assertions; exits 0 on success.

Library:
    check(base, adr_path, fake_diff) -> (rc, violations, warnings)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ADR = "docs/adr/0103-locked-surface-and-port-policy.md"
_SOFT_LOCK_NEEDLE = "wire-shape preserved"
_HARD_SECTION = "### 1. Hard-lock"
_SOFT_SECTION = "### 2. Soft-lock"
_LIST_ITEM = re.compile(r"^-\s+`([^`]+)`")


def _parse_paths(adr: Path, section_marker: str) -> list[str]:
    r"""Extract `` `- `path`` `` entries under `section_marker` until the next `### ` heading."""
    if not adr.exists():
        return []
    paths: list[str] = []
    in_section = False
    for line in adr.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            if in_section:
                break
            if stripped == section_marker:
                in_section = True
            continue
        if not in_section:
            continue
        m = _LIST_ITEM.match(stripped)
        if m:
            paths.append(m.group(1).rstrip("/"))
    return paths


def _hard_paths(adr: Path) -> list[str]:
    return _parse_paths(adr, _HARD_SECTION)


def _soft_paths(adr: Path) -> list[str]:
    return _parse_paths(adr, _SOFT_SECTION)


def _diff_names(base: str) -> list[str]:
    p = subprocess.run(  # noqa: S603
        ["git", "diff", "--name-only", f"{base}..HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return [line.strip() for line in p.stdout.splitlines() if line.strip()]


def _head_message() -> str:
    p = subprocess.run(
        ["git", "log", "-1", "--format=%B"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
    )
    return p.stdout


def _is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def check(
    base: str = "HEAD",
    adr_path: str = _DEFAULT_ADR,
    fake_diff: list[str] | None = None,
) -> tuple[int, list[str], list[str]]:
    """Run the guard logic; return (rc, violations, warnings)."""
    adr = _ROOT / adr_path
    hard = _hard_paths(adr)
    soft = _soft_paths(adr)
    changed = _diff_names(base)
    if fake_diff:
        changed = list({*changed, *fake_diff})
    violations: list[str] = []
    warnings: list[str] = []
    msg = _head_message()
    for path in changed:
        for h in hard:
            if _is_under(path, h):
                violations.append(f"HARD-LOCK: {path} (locked by {h})")
        for s in soft:
            if _is_under(path, s) and _SOFT_LOCK_NEEDLE not in msg:
                warnings.append(
                    f"SOFT-LOCK: {path} — commit body must contain '{_SOFT_LOCK_NEEDLE}'"
                )
    return (1 if violations else 0), violations, warnings


def _self_test() -> int:
    """In-process assertions: ADR parses, hard-lock fails, soft-lock warns."""
    adr = _ROOT / _DEFAULT_ADR
    hard = _hard_paths(adr)
    soft = _soft_paths(adr)
    assert hard, "hard-lock list must be non-empty"
    assert soft, "soft-lock list must be non-empty"
    assert any("deploy/lobehub" in h for h in hard), "hard-lock must include deploy/lobehub"
    assert any("gateway/runs/api.py" in s for s in soft), (
        "soft-lock must include gateway/runs/api.py"
    )

    rc, violations, _ = check(base="HEAD")
    assert rc == 0, f"clean HEAD should pass; got violations={violations}"

    rc, violations, _ = check(
        base="HEAD",
        fake_diff=["deploy/lobehub/patches/runtime/LcaRunDriver.ts"],
    )
    assert rc == 1, "hard-lock diff must fail"
    assert any("deploy/lobehub" in v for v in violations), violations

    rc, _, warnings = check(base="HEAD", fake_diff=["gateway/runs/api.py"])
    assert rc == 0, "soft-lock alone does not fail"
    assert warnings, "soft-lock diff must emit a warning"

    print(f"self-test OK: hard={len(hard)}, soft={len(soft)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--adr", default=_DEFAULT_ADR)
    parser.add_argument(
        "--fake-diff",
        action="append",
        default=[],
        help="Inject synthetic changed path (test hook).",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    rc, violations, warnings = check(
        base=args.base, adr_path=args.adr, fake_diff=args.fake_diff or None
    )
    for v in violations:
        print(v, file=sys.stderr)
    for w in warnings:
        print(w, file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
