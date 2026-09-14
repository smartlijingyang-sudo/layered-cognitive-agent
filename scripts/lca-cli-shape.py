#!/usr/bin/env python3
"""CI gate: enforce CLI surface shape rules for ``lca/infrastructure/cli/commands/**``.

Mirrors the style of ``scripts/check_plugin_shape.py`` (stdlib-only, baseline-
free, exit-0-or-1, structured human output). Three checks:

1. **Shared loader rule** — any file in ``lca/infrastructure/cli/commands/**``
   that defines ``_load_events`` / ``_load_facts`` / ``_read_events_jsonl``
   must either delegate to the public API in
   ``lca.infrastructure.cli.commands._shared.projection`` (any of:
   ``load_spine_events``, ``filter_by_domain``, ``summarize_outputs``,
   ``truncate``, ``spine_filename_for_run_cwd``) OR carry a one-line comment
   ``# non-shared: ...`` that explains the deviation.

   Files in ``SHARED_LOADER_EXEMPT`` (currently ``journal/replay.py`` for
   strict ``EventRecord`` typing, plus the three ``observation/*`` files
   whose filters are EP-prefix-specific) are out of scope with delete-when
   notes. The docstring on ``journal/replay.py`` documents why it does NOT
   call the shared tolerant ``SpineRow`` projection.

2. **OutputMode rule** — every file that exposes ``register(app: typer.Typer)``
   under ``lca/infrastructure/cli/commands/`` and whose sub-commands emit
   structured (JSON-serializable) output must either reference
   ``output_option(...)`` from ``lca.infrastructure.cli.commands._shared.output``
   OR carry the literal ``--json`` flag string (e.g. ``--json/--human`` pair
   or a bare ``--json``). Detection: grep the file for ``output_option(`` or
   ``--json``. Files that do not emit structured output (only text logs,
   file writes, or plain ``print()``) are out of scope; same for files
   carrying a ``# non-shared:`` comment that documents the deviation.

3. **Register function shape** — every CLI command module under
   ``lca/infrastructure/cli/commands/**`` (i.e. a ``.py`` file that is not
   ``__init__.py`` and not in any ``_shared/`` subdir and that uses ``typer``)
   must export a top-level ``def register(app: typer.Typer)`` so it can be
   mounted by the parent sub-app.

Exit codes:
- 0 → all checks pass.
- 1 → one or more findings; printed as a grouped list to stderr.

Usage:
  ./scripts/lca-cli-shape.py
  python3 scripts/lca-cli-shape.py
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS_ROOT = ROOT / "lca" / "infrastructure" / "cli" / "commands"

# Functions whose presence in a file triggers the shared-loader check.
LOADER_FUNCS: tuple[str, ...] = (
    "_load_events",
    "_load_facts",
    "_read_events_jsonl",
)

# Public API names that qualify a file as delegating to the shared loader.
SHARED_PROJECTION_NAMES: tuple[str, ...] = (
    "load_spine_events",
    "filter_by_domain",
    "summarize_outputs",
    "truncate",
    "spine_filename_for_run_cwd",
)

# Files exempt from the shared-loader rule. Kept narrow on purpose; add to
# this list only with an owner + delete-when note in the script's commit msg.
# Each entry MUST carry a delete-when clause: which future PR removes the
# exemption by either delegating to the shared projection layer or by
# carrying a ``# non-shared:`` comment in the file itself.
SHARED_LOADER_EXEMPT: frozenset[str] = frozenset(
    {
        # WaterfallDeriver needs strict EventRecord; the shared tolerant
        # SpineRow projection does not satisfy on_event's type-check.
        # delete-when: PR-6 (journal refactor) folds replay's spine read into
        # a typed helper that exposes EventRecord without changing callers.
        "lca/infrastructure/cli/commands/journal/replay.py",
        # observation/run_explain.py: filters facts by execution_point
        # prefix (``observation.*``/``diagnosis.*``). The shared
        # ``filter_by_domain`` keys on a different meta family
        # (DEBUG_RUN_META_FAMILIES), so swapping the loader would change
        # which rows survive. delete-when: domain projection is unified.
        "lca/infrastructure/cli/commands/observation/run_explain.py",
        # observation/run_replay.py: same as run_explain (filters by EP).
        # delete-when: domain projection is unified.
        "lca/infrastructure/cli/commands/observation/run_replay.py",
        # observation/trace_show.py: same as run_explain (filters by EP +
        # is_graph_event), and the loader returns facts (not generic events).
        # delete-when: domain projection is unified.
        "lca/infrastructure/cli/commands/observation/trace_show.py",
    }
)

# Files exempt from the OutputMode rule. Same shape as SHARED_LOADER_EXEMPT;
# each entry MUST carry a delete-when clause that names the future PR which
# either adopts ``output_option(...)`` or adds a ``--json/--human`` toggle to
# the file's sub-commands.
OUTPUT_MODE_EXEMPT: frozenset[str] = frozenset(
    {
        # journal/replay.py: trajectory writes HTML, verify-model-visible
        # prints text; only ``replay`` emits JSON, but adding a
        # ``--json/--human`` toggle would change the public CLI surface and
        # is out of scope for the PR-5 audit-script PR. delete-when: the
        # next journal refactor adds the toggle to ``replay`` (one sub-cmd
        # out of three) and drops this entry.
        "lca/infrastructure/cli/commands/journal/replay.py",
    }
)

# Markers that exempt a loader function from the shared-loader rule.
NON_SHARED_COMMENT_PREFIX = "# non-shared:"


@dataclass
class Finding:
    """One shape violation; rendered in the human report."""

    kind: str
    file: str
    line: int
    detail: str


@dataclass
class ShapeReport:
    """Aggregated findings across all three checks."""

    root: str
    command_files: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.kind] = out.get(f.kind, 0) + 1
        return out


# ── helpers ──────────────────────────────────────────────────────────────


def _iter_command_py_files(commands_root: Path) -> list[Path]:
    """Walk ``commands_root`` for command Python files.

    Skips ``__init__.py``, any file under a ``_shared/`` subdir at any depth,
    and any file literally named ``_shared.py`` (the kernel package uses
    that single-file helper convention) — those are helper modules, not
    mountable commands.
    """
    out: list[Path] = []
    for path in sorted(commands_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py":
            continue
        rel_parts = path.relative_to(commands_root).parts
        if any(part == "_shared" for part in rel_parts):
            continue
        if path.name == "_shared.py":
            continue
        out.append(path)
    return out


def _parse_tree(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _is_command_module(path: Path, source: str, tree: ast.Module | None) -> bool:
    """A file counts as a CLI command module if it touches ``typer``.

    ``_shared`` and ``__init__`` are already filtered upstream; the remaining
    signal is: does the file reference ``typer.Typer`` (import or usage) or
    decorate a function with ``@app.command(`` / ``app.command(``?
    """
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "typer":
                return True
            if isinstance(node, ast.Attribute) and node.attr in {"Typer", "Command", "Option", "Argument"}:
                return True
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"command", "add_typer"}
            ):
                return True
    # Fallback: textual match (covers compiled/cached files we cannot parse).
    return "typer" in source and ("app.command" in source or "typer.Typer" in source)


def _has_register_function(tree: ast.Module | None) -> tuple[bool, int]:
    """Top-level ``def register(app: typer.Typer, ...) -> ...`` check.

    The canonical first parameter is ``app: typer.Typer``. Additional
    parameters after ``app`` (e.g. ``group: typer.Typer | None = None`` in
    ``journal/journal.py``) are accepted because they preserve the
    ``register(app, ...)`` mounting contract — the parent sub-app still
    passes a single ``app`` positional when calling the canonical form.
    Returns ``(ok, line)``; ``line`` is 0 when missing.
    """
    if tree is None:
        return False, 0
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "register":
            continue
        args = node.args
        if not args.args:
            continue
        first = args.args[0]
        if first.arg != "app":
            continue
        ann = first.annotation
        if not isinstance(ann, ast.Attribute):
            continue
        if ann.attr != "Typer":
            continue
        return True, node.lineno
    return False, 0


def _has_non_shared_comment(path: Path) -> bool:
    """Check whether the file carries a ``# non-shared: ...`` line.

    The comment is accepted at module level (top of the file) or directly
    above the loader function definition.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(NON_SHARED_COMMENT_PREFIX):
            return True
    return False


def _delegates_to_shared_loader(source: str) -> bool:
    """A file delegates to the shared loader if it imports any public helper
    from ``lca.infrastructure.cli.commands._shared.projection``."""
    imports_shared_projection = (
        "_shared.projection" in source
        or ("_shared import" in source and "projection" in source)
    )
    if not imports_shared_projection:
        return False
    return any(name in source for name in SHARED_PROJECTION_NAMES)


def _uses_output_option(source: str) -> bool:
    """A file conforms to the OutputMode rule if it uses ``output_option(``
    from the shared module OR carries the ``--json`` flag string."""
    if "output_option(" in source:
        return True
    return "--json" in source


# ── checks ───────────────────────────────────────────────────────────────


def _check_shared_loader(commands_root: Path) -> list[Finding]:
    """Check 1: shared loader delegation rule.

    Skips files in ``SHARED_LOADER_EXEMPT`` (see delete-when clauses for
    each entry). For every other file that defines one of ``LOADER_FUNCS``,
    the file must either import from the shared projection module OR carry
    a ``# non-shared: ...`` comment.
    """
    out: list[Finding] = []
    for path in _iter_command_py_files(commands_root):
        rel = path.relative_to(ROOT).as_posix()
        if rel in SHARED_LOADER_EXEMPT:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        tree = _parse_tree(path)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in LOADER_FUNCS:
                continue
            if _delegates_to_shared_loader(source):
                continue
            if _has_non_shared_comment(path):
                continue
            out.append(
                Finding(
                    kind="shared_loader",
                    file=rel,
                    line=node.lineno,
                    detail=(
                        f"{node.name}() 不调用 _shared.projection 公共 API,"
                        " 且无 '# non-shared:' 注释说明"
                    ),
                )
            )
    return out


def _emits_structured_output(source: str, tree: ast.Module | None) -> bool:
    """Heuristic: does the file emit structured (JSON-serializable) output?

    Looks for ``typer.echo(json.dumps(...``, ``.model_dump(``, or
    ``OutputMode`` usage. Commands that only emit plain text, file paths, or
    HTML do not match — they have no use for ``--json/--human`` toggles.
    """
    if tree is not None:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"model_dump", "model_dump_json"}
            ):
                return True
            if isinstance(node, ast.Name) and node.id == "OutputMode":
                return True
    # Textual fallback (catches "typer.echo(json.dumps(...)" etc.)
    if "json.dumps(" in source and "typer.echo" in source:
        return True
    if "model_dump" in source:
        return True
    return "OutputMode" in source


def _check_output_mode(commands_root: Path) -> list[Finding]:
    """Check 2: every CLI command module that emits structured output must
    use ``output_option(...)`` or the ``--json/--human`` boolean pair.

    Scope: files that expose a top-level ``def register(app: typer.Typer)``
    AND whose body actually serializes a payload (``typer.echo(json.dumps(``,
    ``.model_dump(``, or ``OutputMode``). Commands that only write files,
    tail logs, or render plain text (e.g. ``journal/replay.py`` trajectory
    → HTML, ``runs/diagnostics.py`` → ``print(...)``) are out of scope: the
    ``--json/--human`` toggle has no payload to switch. Files listed in
    ``OUTPUT_MODE_EXEMPT`` are also out of scope, with documented
    delete-when clauses.
    """
    out: list[Finding] = []
    for path in _iter_command_py_files(commands_root):
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        tree = _parse_tree(path)
        if tree is None:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in OUTPUT_MODE_EXEMPT:
            continue
        ok, line = _has_register_function(tree)
        if not ok:
            continue  # check 3 owns register-shape violations
        if not _emits_structured_output(source, tree):
            continue
        if _uses_output_option(source):
            continue
        if _has_non_shared_comment(path):
            continue
        out.append(
            Finding(
                kind="output_mode",
                file=rel,
                line=line,
                detail=(
                    "register() 暴露的子命令既未用 output_option(...) 也未用"
                    " --json/--human 标志对"
                ),
            )
        )
    return out


def _check_register_shape(commands_root: Path) -> list[Finding]:
    """Check 3: every CLI command module exports ``register(app: typer.Typer)``.

    A "CLI command module" is a file under ``commands/**/`` that is not
    ``__init__.py``, not in any ``_shared/`` subdir, and that uses ``typer``.
    Helper modules (no typer) are not subject to this rule.
    """
    out: list[Finding] = []
    for path in _iter_command_py_files(commands_root):
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        tree = _parse_tree(path)
        if not _is_command_module(path, source, tree):
            continue
        ok, _line = _has_register_function(tree)
        rel = path.relative_to(ROOT).as_posix()
        if not ok:
            out.append(
                Finding(
                    kind="register_shape",
                    file=rel,
                    line=0,
                    detail="缺少顶层 def register(app: typer.Typer)",
                )
            )
    return out


# ── main ─────────────────────────────────────────────────────────────────


def scan(commands_root: Path) -> ShapeReport:
    """Run all three checks; aggregate into a single report."""
    command_files = _iter_command_py_files(commands_root)
    findings = (
        _check_shared_loader(commands_root)
        + _check_output_mode(commands_root)
        + _check_register_shape(commands_root)
    )
    return ShapeReport(
        root=str(commands_root),
        command_files=len(command_files),
        findings=findings,
    )


def emit_human(report: ShapeReport) -> None:
    """Render findings as a human-readable grouped list on stderr."""
    if not report.findings:
        print(
            f"cli-shape: all {report.command_files} command files follow"
            " the shared-loader / output-mode / register-shape conventions."
        )
        return
    print(
        f"cli-shape: scanned {report.command_files} command files under"
        f" {report.root}; findings={report.by_kind}",
        file=sys.stderr,
    )
    grouped: dict[str, list[Finding]] = {}
    for f in report.findings:
        grouped.setdefault(f.kind, []).append(f)
    labels = {
        "shared_loader": "[shared loader 未委托]",
        "output_mode": "[OutputMode/--json 未规范]",
        "register_shape": "[register 函数缺失]",
    }
    for kind, items in grouped.items():
        print(f"\n{labels.get(kind, f'[{kind}]')} ({len(items)} 个)", file=sys.stderr)
        for v in items:
            print(f"  {v.file}:{v.line}  {v.detail}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print(f"unexpected arguments: {argv}", file=sys.stderr)
        return 2
    if not COMMANDS_ROOT.is_dir():
        print(f"commands root not found: {COMMANDS_ROOT}", file=sys.stderr)
        return 2
    report = scan(COMMANDS_ROOT)
    emit_human(report)
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())
