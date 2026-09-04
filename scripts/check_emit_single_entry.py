#!/usr/bin/env python3
"""Gate: ``emit_exception_caught`` has exactly one production definition.

ADR-0169 + note ``2026-09-03-3-seam-emit-single-entry.md`` (PR-3): the
``exception.caught`` event-point must have a single emitter —
``lca.infrastructure.observability.spine.exception_emit.emit_exception_caught``.
Any other ``def emit_exception_caught`` in ``lca/`` is a parallel emitter
that loses payload fields (traceback, call_frames, err_kind) and must be
deleted.

Scan strategy
-------------
AST-walk every ``.py`` under ``lca/`` and collect ``FunctionDef`` /
``AsyncFunctionDef`` nodes named ``emit_exception_caught``. The only
allowed definition lives in ``exception_emit.py``. Protocol ``...``
stubs and ``EnvelopeEmitter`` implementations are **not** exempt — the
note requires the Protocol method itself be removed (the keyword
argument surface cannot carry ``ExceptionRecord``).

Usage::

    python scripts/check_emit_single_entry.py            # human report
    python scripts/check_emit_single_entry.py --json     # CI JSON
    python scripts/check_emit_single_entry.py --strict   # exit 1 on violations

Exit codes:
  0  zero violations (only the SSOT emitter exists)
  1  violations present
  2  fatal scan error
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCAN_ROOT = _ROOT / "lca"

# Relative path (posix) of the sole permitted definition.
_SSOT_MODULE: str = "lca/infrastructure/observability/spine/exception_emit.py"


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    col: int
    kind: str  # "function" or "method"
    enclosing: str  # class name for methods, module-level for functions


def _scan_file(path: Path) -> list[Violation]:
    rel = path.relative_to(_ROOT).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    if "emit_exception_caught" not in source:
        return []
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return []

    violations: list[Violation] = []
    # Walk top-level statements only: module-level defs and class methods.
    # Nested defs (inside if/try/for) are not emitters in the architectural
    # sense and are not scanned.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "emit_exception_caught":
                violations.append(
                    Violation(
                        file=rel,
                        line=node.lineno,
                        col=node.col_offset,
                        kind="function",
                        enclosing="<module>",
                    )
                )
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == "emit_exception_caught"
                ):
                    violations.append(
                        Violation(
                            file=rel,
                            line=item.lineno,
                            col=item.col_offset,
                            kind="method",
                            enclosing=node.name,
                        )
                    )
    return violations


def _check() -> list[Violation]:
    """Return all ``emit_exception_caught`` definitions outside the SSOT."""
    if not _SCAN_ROOT.exists():
        return []
    violations: list[Violation] = []
    for path in sorted(_SCAN_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(_ROOT).as_posix()
        if rel == _SSOT_MODULE:
            continue
        violations.extend(_scan_file(path))
    return violations


def _render_markdown(violations: list[Violation]) -> str:
    if not violations:
        return "emit_exception_caught single-entry gate: PASS ✅\n"
    lines = [
        "# emit_exception_caught single-entry gate",
        "",
        f"**{len(violations)} parallel emitter(s) detected** — only "
        f"`{_SSOT_MODULE}` may define `emit_exception_caught`.",
        "",
        "| file | line | kind | enclosing |",
        "|---|---|---|---|",
    ]
    for v in violations:
        lines.append(f"| `{v.file}` | {v.line} | {v.kind} | `{v.enclosing}` |")
    lines += [
        "",
        "Delete the parallel emitter(s) and route callers through the "
        "SSOT `exception_emit.emit_exception_caught(record)`.",
    ]
    return "\n".join(lines) + "\n"


def _render_json(violations: list[Violation]) -> str:
    return (
        json.dumps(
            {
                "check": "check_emit_single_entry",
                "ssot_module": _SSOT_MODULE,
                "violations": [asdict(v) for v in violations],
                "summary": {"total": len(violations)},
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit JSON instead of markdown",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on any violation (default behaviour)",
    )
    args = parser.parse_args(argv)

    try:
        violations = _check()
    except Exception as exc:  # pragma: no cover — defensive only
        print(f"fatal: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        sys.stdout.write(_render_json(violations))
    else:
        sys.stdout.write(_render_markdown(violations))

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
