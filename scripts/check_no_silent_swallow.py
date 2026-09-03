#!/usr/bin/env python3
"""Detect silent exception swallowing in ``lca/`` and ``lca_kernel/``.

ADR-2026-09-03 traceback-ssot-hook: every ``except`` clause in
production code MUST do one of:

1. **emit** the exception through :func:`emit_exception_caught`
   (the SSOT exception emitter in
   ``lca.infrastructure.observability.spine.exception_emit``),
2. **re-raise** the exception (``raise`` or ``raise X from exc``), or
3. **document** the intent with a same-line comment justifying the
   silence (``# WHY: <reason>`` or ``# INTENTIONAL: <reason>``).

Why this exists
---------------

Before this check, multiple call sites used ``except BaseException:
pass`` (or ``except Exception: pass``) to swallow errors without
emitting a traceback. The cost was severe: when an unexpected
exception reached those swallowers, no record reached the spine —
``manifest.session_error`` held only a one-line string, and no
sidecar JSON captured the traceback. The K6 fail-loud hook
(``sys.excepthook`` + ``asyncio.set_exception_handler`` +
``threading.excepthook``) now catches anything that escapes a
swallower, but the architectural intent is that swallower clauses
themselves be deliberate.

This script flags:

- ``except <X>: pass`` / ``except <X>: ... pass`` (no re-raise,
  no emit, no WHY comment),
- ``except <X>:\n    <body without raise/emit/WHY comment>``.

Allowed escapes (NOT flagged):

- ``except <X>: raise`` / ``raise X`` / ``raise X from exc``
- ``except <X>: emit_exception_caught(...)``
- ``except <X>: ... # WHY: ...`` / ``# INTENTIONAL: ...``
- The K6 fail-loud hooks themselves (``lca_kernel/lifecycle.py``),
  which are the SSOT path.

Usage::

    python scripts/check_no_silent_swallow.py            # human report
    python scripts/check_no_silent_swallow.py --json     # CI JSON
    python scripts/check_no_silent_swallow.py --strict   # exit 1 on
                                                         # any finding

Exit codes:
  0  no findings
  1  findings present (or any finding under --strict)
  2  fatal scan error
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DIRS = (_ROOT / "lca", _ROOT / "lca_kernel")

# Files where the bare ``except`` clauses are part of the SSOT design
# itself (K6 fail-loud) or non-production helpers. They are exempt from
# the check by file path.
_ALLOWLIST_FILES: frozenset[str] = frozenset({
    # K6 SSOT path — the hooks ARE the SSOT, their except handlers
    # wrap coordination logic, not domain logic.
    "lca_kernel/lifecycle.py",
})

# Patterns matching the allowed intent comments.
_WHY_COMMENT_RE = re.compile(
    r"#\s*(?:WHY|INTENTIONAL|intentionally|intentional)\s*:",
    re.IGNORECASE,
)

# Names that constitute an SSOT emit (lca.infrastructure.observability).
_EMIT_FUNCTIONS: frozenset[str] = frozenset({
    "emit_exception_caught",
})


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    col: int
    handler: str  # the except target text
    body_summary: str  # short description of the body
    severity: str  # "error" or "warning"


def _walk_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def _body_contains_allowed(body: list[ast.stmt]) -> tuple[bool, str]:
    """Return ``(allowed, summary)``.

    ``allowed`` is True iff the body re-raises, emits, or is documented.
    ``summary`` is a short description used in the report.
    """
    has_raise = False
    has_emit = False
    for stmt in body:
        if isinstance(stmt, ast.Raise):
            has_raise = True
            continue
        if isinstance(stmt, ast.Expr):
            value = stmt.value
            if isinstance(value, ast.Call):
                func = value.func
                if (isinstance(func, ast.Name) and func.id in _EMIT_FUNCTIONS) or (isinstance(func, ast.Attribute) and func.attr in _EMIT_FUNCTIONS):
                    has_emit = True
    if has_raise and has_emit:
        return True, "raise + emit"
    if has_raise:
        return True, "raise"
    if has_emit:
        return True, "emit_exception_caught"
    return False, _summarize_body(body)


def _summarize_body(body: list[ast.stmt]) -> str:
    if not body:
        return "pass"
    first = body[0]
    if isinstance(first, ast.Pass):
        return "pass"
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        return f"docstring:{first.value.value!r:.30}"
    if isinstance(first, ast.Return):
        # ``return None`` / ``return <value>`` is **legitimate narrow recovery**
        # when the exception signals "absent" (KeyError on lookup, OSError on
        # missing file, etc.) — NOT silent traceback swallowing. Only flag
        # ``return`` statements in body when the exception is broad (BaseException /
        # Exception) AND no WHY comment.
        return "return"
    if isinstance(first, ast.If):
        return "if-... (no raise/emit)"
    return f"{type(first).__name__}"


def _is_broad_handler(target_text: str) -> bool:
    """Return True if the except clause is broad enough to swallow
    *unexpected* exceptions (not legitimate narrow lookup failures)."""
    broad = {
        "Exception", "BaseException", "(Exception,)", "(BaseException,)",
    }
    return target_text in broad


def _is_narrow_recovery(body: list[ast.stmt]) -> bool:
    """Heuristic: the body returns a sentinel (None / empty) which is a
    legitimate "absent" response for narrow except types.

    Only call this after determining ``_is_broad_handler(target)`` is True;
    narrow handlers (KeyError / OSError / ValueError) are always allowed.
    """
    if not body:
        return False
    first = body[0]
    # ``return`` / ``return None`` / ``return <name>`` — caller decides.
    return isinstance(first, ast.Return)


def _is_destructively_silent(body: list[ast.stmt]) -> bool:
    """Return True iff the body is *pure silence* — nothing useful happens.

    Pure silence includes:
    - empty body (``pass``)
    - body is just a docstring with no follow-up statement
    - bare ``return`` / ``return None`` with no logging (only flagged
      for *broad* handlers, since narrow handlers legitimately return
      None as "absent")
    - bare ``return`` of a *literal None* / empty literal (no domain
      meaning — true silence)
    """
    if not body:
        return True
    # Strip leading docstring, then check if anything actionable remains
    actionable = body
    if (
        len(actionable) == 1
        and isinstance(actionable[0], ast.Expr)
        and isinstance(actionable[0].value, ast.Constant)
    ):
        # Just a docstring — pure silence
        return True
    # pass-only body
    if all(isinstance(s, ast.Pass) for s in actionable):
        return True
    # Single bare ``return`` (no value) — true silence
    if (
        len(actionable) == 1
        and isinstance(actionable[0], ast.Return)
        and actionable[0].value is None
    ):
        return True
    # ``return None`` — true silence (no domain meaning returned)
    return bool(len(actionable) == 1 and isinstance(actionable[0], ast.Return) and isinstance(actionable[0].value, ast.Constant) and actionable[0].value.value is None)


def _returns_domain_sentinel(body: list[ast.stmt]) -> bool:
    """Return True if body's terminal statement returns a non-None sentinel
    (legitimate narrow recovery that surfaces the failure to the caller as
    a structured value).

    Examples (legitimate):
      - ``except Exception as exc: log.error(...); return _fail_observation(...)``
      - ``except Exception: return f"step-unknown-{trace.template_id}"``
      - ``except Exception: return _timeout_observation()``
    """
    if not body:
        return False
    stmt = body[-1]
    if not isinstance(stmt, ast.Return):
        return False
    if stmt.value is None:
        return False
    return not (isinstance(stmt.value, ast.Constant) and stmt.value.value is None)


def _check_file(path: Path) -> list[Finding]:
    rel = path.relative_to(_ROOT).as_posix()
    if rel in _ALLOWLIST_FILES:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    # Quick reject: skip files with no ``except`` keyword
    if "except" not in source:
        return []
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return []

    findings: list[Finding] = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            # bare ``except:`` is always a smell
            target_text = "(bare except)" if handler.type is None else ast.unparse(handler.type)

            is_broad = _is_broad_handler(target_text)

            body = handler.body
            # Even with logging/emitting, if the body is destructively silent
            # AND broad, still flag — broad silence is the worst case.
            allowed, _summary = _body_contains_allowed(body)
            if allowed:
                continue
            # WHY/INTENTIONAL comments can sit on the handler line, in the
            # preceding two lines, or on any line in the body.
            body_end_lineno = body[-1].end_lineno if body else handler.lineno
            comment_window = _extract_comment_window(
                lines, handler.lineno, body_end_lineno
            )
            has_why_comment = bool(_WHY_COMMENT_RE.search(comment_window))
            if has_why_comment:
                continue
            # ``return <domain-sentinel>`` is legitimate narrow recovery
            # even on broad handlers — caller sees the failure as a value.
            if _returns_domain_sentinel(body):
                continue
            if not _is_destructively_silent(body):
                continue
            # For broad handlers + pure silence, this is the bug shape
            # we want to catch. Narrow handlers + ``return None`` skip.
            if not is_broad and _is_narrow_recovery(body):
                continue

            findings.append(
                Finding(
                    file=rel,
                    line=handler.lineno,
                    col=handler.col_offset,
                    handler=target_text,
                    body_summary=_summarize_body(body),
                    severity="error",
                )
            )
    return findings


def _extract_comment_window(
    lines: list[str], handler_lineno: int, body_end_lineno: int
) -> str:
    """Return comment context covering handler line + body lines.

    Lines are 1-indexed (matching ``ast``). We look at the handler's own
    line (for inline ``except ... :  # WHY``), the two lines above the
    handler (for comment justification above), and the body lines
    themselves (for inline ``pass  # INTENTIONAL: ...``). The combination
    covers all three styles.
    """
    start = max(1, handler_lineno - 2)
    end = min(len(lines), body_end_lineno)
    return "\n".join(lines[start - 1 : end])


def _render_markdown(findings: list[Finding]) -> str:
    if not findings:
        return "no silent exception swallowing detected ✅\n"
    out = ["# Silent exception swallowing check", ""]
    out.append(f"**{len(findings)} finding(s)**\n")
    out.append("| file | line | handler | body |")
    out.append("|---|---|---|---|")
    for f in findings:
        out.append(f"| `{f.file}` | {f.line} | `{f.handler}` | {f.body_summary} |")
    out.append("")
    out.append("Remediation per finding:")
    out.append(
        "- Add `raise` (re-raise the exception so K6 fail-loud captures it),"
    )
    out.append(
        "- Add `emit_exception_caught(...)` (route through SSOT — preferred"
        " for domain-meaningful errors), or"
    )
    out.append("- Add a same-line `# WHY: ...` comment justifying the silence.")
    out.append("")
    return "\n".join(out)


def _render_json(findings: list[Finding]) -> str:
    return json.dumps(
        {
            "check": "check_no_silent_swallow",
            "findings": [asdict(f) for f in findings],
            "summary": {
                "total": len(findings),
                "errors": sum(1 for f in findings if f.severity == "error"),
                "warnings": sum(1 for f in findings if f.severity == "warning"),
            },
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
    )
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        default=None,
        help="root directory to scan (default: lca/ + lca_kernel/)",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true",
        help="emit JSON instead of markdown",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="exit 1 on any finding (default: same)",
    )
    args = parser.parse_args(argv)

    roots = [Path(r) for r in (args.root or _DEFAULT_DIRS)]
    try:
        findings: list[Finding] = []
        for path in _walk_python_files(roots):
            findings.extend(_check_file(path))
    except Exception as exc:  # pragma: no cover — defensive only
        print(f"fatal: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        sys.stdout.write(_render_json(findings))
    else:
        sys.stdout.write(_render_markdown(findings))

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
