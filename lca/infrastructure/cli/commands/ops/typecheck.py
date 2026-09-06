"""Static type checking — Mypy + Pyright (Pylance) in one command."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import typer

from lca.infrastructure.cli.commands.kernel._shared import resolve_repo_root

_MYPY_ERROR = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+)(?::(?P<col>\d+))?"
    r": error: (?P<message>.+?)(?:\s+\[(?P<code>[^\]]+)\])?$"
)
_PYRIGHT_ERROR = re.compile(
    r"^\s*(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+)"
    r" - error: (?P<message>.+?) \((?P<code>[^)]+)\)$"
)
_SUMMARY_MYPY = re.compile(r"Found (\d+) error")
_SUMMARY_PYRIGHT = re.compile(r"(\d+) errors?")


@dataclass(frozen=True, slots=True)
class TypeDiagnostic:
    tool: str
    path: str
    line: int
    column: int | None
    message: str
    code: str


_DEFAULT_PATHS = ["lca"]


def _run_tool(cmd: list[str], *, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output


def _parse_mypy(output: str) -> list[TypeDiagnostic]:
    diagnostics: list[TypeDiagnostic] = []
    for line in output.splitlines():
        match = _MYPY_ERROR.match(line.strip())
        if match is None:
            continue
        diagnostics.append(
            TypeDiagnostic(
                tool="mypy",
                path=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("col")) if match.group("col") else None,
                message=match.group("message"),
                code=match.group("code") or "error",
            )
        )
    return diagnostics


def _parse_pyright(output: str) -> list[TypeDiagnostic]:
    diagnostics: list[TypeDiagnostic] = []
    for line in output.splitlines():
        match = _PYRIGHT_ERROR.match(line)
        if match is None:
            continue
        diagnostics.append(
            TypeDiagnostic(
                tool="pyright",
                path=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("col")),
                message=match.group("message"),
                code=match.group("code"),
            )
        )
    return diagnostics


def _summary_count(output: str, tool: str) -> int | None:
    if tool == "mypy":
        match = _SUMMARY_MYPY.search(output)
        return int(match.group(1)) if match else None
    match = _SUMMARY_PYRIGHT.search(output)
    return int(match.group(1)) if match else None


def _filter_focus(diagnostics: list[TypeDiagnostic], focus: str) -> list[TypeDiagnostic]:
    if not focus or focus == "all":
        return diagnostics
    if focus == "callable":
        def _is_callable(d: TypeDiagnostic) -> bool:
            msg = d.message.lower()
            if d.code == "reportCallIssue":
                return True
            if "not callable" in msg:
                return True
            if "__call__" in d.message:
                return True
            return d.code == "operator" and "callable" in msg

        return [d for d in diagnostics if _is_callable(d)]
    if focus == "lazy-import":
        needles = (
            "not callable",
            "has no attribute",
            "attr-defined",
            "reportAttributeAccessIssue",
            "module",
            "object",
        )
        return [
            d
            for d in diagnostics
            if any(n.lower() in d.message.lower() or n in d.code for n in needles)
        ]
    msg = f"unknown focus {focus!r}; use callable | lazy-import | all"
    raise typer.BadParameter(msg)


def _format_human(
    *,
    paths: list[str],
    results: list[tuple[str, int, str, list[TypeDiagnostic]]],
    focus: str,
) -> str:
    lines = [f"Typecheck ({', '.join(paths)})", "─" * 40]
    total = 0
    for tool, exit_code, raw, diagnostics in results:
        count = _summary_count(raw, tool)
        if count is None:
            count = len(diagnostics)
        total += count
        status = "ok" if exit_code == 0 else "fail"
        lines.append(f"{tool:8} {count:4} diagnostics  exit {exit_code} ({status})")
    shown: list[TypeDiagnostic] = []
    for _, _, _, diagnostics in results:
        shown.extend(diagnostics)
    shown = _filter_focus(shown, focus)
    if focus and focus != "all":
        lines.append("")
        lines.append(f"Focus {focus!r} ({len(shown)}):")
        for diag in shown[:50]:
            col = f":{diag.column}" if diag.column is not None else ""
            lines.append(
                f"  {diag.path}:{diag.line}{col}  [{diag.tool} {diag.code}]  {diag.message}"
            )
        if len(shown) > 50:
            lines.append(f"  … and {len(shown) - 50} more (use --json)")
    else:
        lines.append("")
        lines.append("Tip: --focus callable | lazy-import  ·  --json for full diagnostics")
    lines.append("")
    lines.append("ok" if total == 0 else f"failed — {total} diagnostics")
    return "\n".join(lines)


def run_typecheck(
    paths: list[str],
    *,
    repo_root: Path,
    mypy_only: bool = False,
    pyright_only: bool = False,
    focus: str = "",
) -> tuple[int, list[tuple[str, int, str, list[TypeDiagnostic]]]]:
    targets = paths or ["lca"]
    runners: list[tuple[str, list[str]]] = []
    if not pyright_only:
        runners.append(("mypy", ["uv", "run", "mypy", *targets]))
    if not mypy_only:
        runners.append(("pyright", ["uv", "run", "pyright", *targets]))

    results: list[tuple[str, int, str, list[TypeDiagnostic]]] = []
    worst_exit = 0
    for tool, cmd in runners:
        exit_code, output = _run_tool(cmd, cwd=repo_root)
        worst_exit = max(worst_exit, exit_code)
        parser = _parse_mypy if tool == "mypy" else _parse_pyright
        results.append((tool, exit_code, output, parser(output)))
    return worst_exit, results


def register(app: typer.Typer) -> None:
    """Register ``typecheck`` on the typer app."""

    @app.command(name="typecheck")
    def typecheck_cmd(
        paths: list[str] | None = typer.Argument(
            None,
            help="Paths to check (default: lca). Example: lca/plugins/transport",
        ),
        json_mode: bool = typer.Option(False, "--json", help="JSON output for agents"),
        mypy_only: bool = typer.Option(False, "--mypy-only", help="Run Mypy only"),
        pyright_only: bool = typer.Option(
            False,
            "--pyright-only",
            help="Run Pyright only (same engine as Pylance)",
        ),
        focus: str = typer.Option(
            "",
            "--focus",
            help="Filter: callable | lazy-import | all (default: show sample)",
        ),
    ) -> None:
        """Run Mypy + Pyright and list type errors (IDE red squiggles at CLI scale).

        Ruff does not perform type checking. Use this before push when VS Code
        Problems panel is noisy or after changing lazy re-exports / Protocols.

        Examples::

            ./scripts/lca-ops typecheck
            ./scripts/lca-ops typecheck --focus callable
            ./scripts/lca-ops typecheck --json
            ./scripts/lca-ops typecheck lca/plugins/transport --pyright-only
        """
        if mypy_only and pyright_only:
            raise typer.BadParameter("Choose at most one of --mypy-only / --pyright-only")

        targets = paths if paths else _DEFAULT_PATHS
        repo_root = resolve_repo_root()
        exit_code, results = run_typecheck(
            targets,
            repo_root=repo_root,
            mypy_only=mypy_only,
            pyright_only=pyright_only,
            focus=focus,
        )

        if json_mode:
            all_diags: list[TypeDiagnostic] = []
            for _, _, _, diags in results:
                all_diags.extend(diags)
            filtered = _filter_focus(all_diags, focus or "all")
            payload = {
                "paths": targets,
                "exit_code": exit_code,
                "tools": [
                    {
                        "tool": tool,
                        "exit_code": tool_exit,
                        "summary_count": _summary_count(raw, tool),
                        "diagnostics": [asdict(d) for d in diags],
                    }
                    for tool, tool_exit, raw, diags in results
                ],
                "filtered": [asdict(d) for d in filtered],
                "filtered_count": len(filtered),
            }
            sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
            sys.stdout.write("\n")
        else:
            sys.stdout.write(
                _format_human(paths=targets, results=results, focus=focus or "all")
            )
            sys.stdout.write("\n")

        raise typer.Exit(exit_code)


__all__ = ["TypeDiagnostic", "register", "run_typecheck"]
