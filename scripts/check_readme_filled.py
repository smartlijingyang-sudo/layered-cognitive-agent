"""Phase D: ensure high-exposure package READMEs are filled out.

Per naming-constitution §6 and the Phase E spec, the auto-scaffolded
``README.md`` for a package contains placeholders like ``{{inputs}}``,
``{{outputs}}``, ``{{failure_semantics}}``. A filled README must
replace those placeholders with concrete text; a passing check
verifies the four required sections are not the auto-generated template.

Usage::

    python scripts/check_readme_filled.py [--root PATH]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PLACEHOLDER_PATTERNS = (
    r"\{\{[a-z_]+\}\}",                # {{placeholder}}
    r"lca\.[a-z_]+: .* 由脚手架生成",    # "X: 由脚手架生成，待包负责人补充具体细节。"
    r"^（无显式 __all__）",            # empty __all__ placeholder
)
PLACEHOLDER_RE = [re.compile(p) for p in PLACEHOLDER_PATTERNS]

REQUIRED_SECTIONS = ("## 1. 职责", "## 2. 不负责", "## 7. 副作用")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca")
    args = parser.parse_args(argv)

    violations: list[str] = []
    for readme in sorted(args.root.rglob("README.md")):
        rel = readme.relative_to(args.root.parent).as_posix()
        text = readme.read_text(encoding="utf-8")
        # Skip non-package root READMEs (those are tool-side guides, e.g.
        # the top-level repository README).
        # Heuristic: only inspect README.md whose directory contains __init__.py.
        if not (readme.parent / "__init__.py").exists():
            continue
        for pattern in PLACEHOLDER_RE:
            if pattern.search(text):
                violations.append(f"{rel}: still contains scaffold placeholder")
                break
        else:
            for section in REQUIRED_SECTIONS:
                if section not in text:
                    violations.append(f"{rel}: missing section {section!r}")

    if not violations:
        print("readme-filled: every package README is filled out.")
        return 0
    for line in violations:
        print(f"  ✗ {line}", file=sys.stderr)
    print(
        f"readme-filled: {len(violations)} README(s) still need filling.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
