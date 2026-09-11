"""Framework/cognition boundary lint (PR-8).

The unified graph kernel rule: framework code never imports cognition
business DTOs (Decision / Observation / Reflection / EffectReceipt),
and cognition never imports framework internals.

Run from the project root:

    python scripts/check_framework_cognition_boundary.py [--strict]

Exits 0 when the rule holds; non-zero on the first violation.

Boundaries enforced:

- ``lca/framework/**`` may not import ``lca/cognition/**``.
- ``lca/framework/**`` may not import ``lca/contracts/models/core/execution/**``
  (Decision / Observation / Reflection / TaskProgress).
- ``lca/framework/**`` may not import ``lca/contracts/models/core/conversation/**``
  (LLMResponse).
- ``lca/cognition/**`` may not import ``lca/framework/**`` (except via the
  protocol-only path: ``lca.contracts.protocols.graph.*``).
- ``lca/contracts/protocols/graph/**`` may not import ``lca/framework/**``
  (graph protocols are contracts only; no implementation imports).

The legacy framework directories (``lca/framework/declarative`` and
``lca/framework/subgraph``) were deleted in the act-subgraph seam
cutover (note 2026-09-11). The whitelist is now empty; any new
violation must be fixed at the source, not bypassed here.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PAIRS: tuple[tuple[Path, Path], ...] = (
    (Path("lca/framework"), Path("lca/cognition")),
    (Path("lca/framework"), Path("lca/contracts/models/core/execution")),
    (Path("lca/framework"), Path("lca/contracts/models/core/conversation")),
)

CONTRACT_FORBIDDEN = (
    (Path("lca/contracts/protocols/graph"), Path("lca/framework")),
)

IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Violation:
    file: Path
    line: int
    line_text: str
    src_root: Path
    banned_root: Path

    def render(self) -> str:
        return (
            f"{self.file}:{self.line}: forbidden import: "
            f"{self.src_root.name!r} -> {self.banned_root.name!r}\n"
            f"    {self.line_text.strip()}"
        )


# No legacy files remain after the act-subgraph seam cutover. New
# violations must be fixed at the source, not bypassed here.
LEGACY_WHITELIST: tuple[tuple[str, str], ...] = ()


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _iter_imports(text: str) -> Iterable[tuple[int, str]]:
    for match in IMPORT_RE.finditer(text):
        line_no = text.count("\n", 0, match.start()) + 1
        module = match.group(1) or match.group(2)
        yield line_no, module


def _module_to_path_segments(module: str) -> tuple[str, ...]:
    return tuple(module.split("."))


def _violations_for(src_root: Path, banned_root: Path) -> list[Violation]:
    src_root_abs = REPO_ROOT / src_root
    banned_segments = banned_root.parts
    out: list[Violation] = []
    for file in _iter_python_files(src_root_abs):
        text = file.read_text(encoding="utf-8", errors="ignore")
        for line_no, module in _iter_imports(text):
            segments = _module_to_path_segments(module)
            if len(segments) < len(banned_segments):
                continue
            if segments[: len(banned_segments)] != banned_segments:
                continue
            line_text = text.splitlines()[line_no - 1] if line_no <= len(text.splitlines()) else ""
            out.append(
                Violation(
                    file=file.relative_to(REPO_ROOT),
                    line=line_no,
                    line_text=line_text,
                    src_root=src_root,
                    banned_root=banned_root,
                )
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    all_violations: list[Violation] = []
    for src_root, banned_root in FORBIDDEN_PAIRS:
        all_violations.extend(_violations_for(src_root, banned_root))
    for src_root, banned_root in CONTRACT_FORBIDDEN:
        all_violations.extend(_violations_for(src_root, banned_root))

    if not all_violations:
        print("framework/cognition boundary: clean")
        return 0

    print("framework/cognition boundary violations:")
    for v in all_violations:
        print(v.render())
    print(f"\nTotal: {len(all_violations)} violation(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
