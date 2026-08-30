"""Audit direct ``sandbox`` / ``transport`` calls in Body code.

Bodies and effect-dispatchers should reach world-side effects via
:class:`~lca.layer1_cognitive.body.safe_executor.SafeExecutor` or via
seams, not by touching ``lca.infrastructure.sandbox`` /
``lca.infrastructure.transport`` directly.

This module scans candidate Body sources (pure ``ast.parse`` — never
imports the scanned code) and reports:

* ``direct_layer0_import`` — an ``import`` / ``from ... import`` whose
  module path is rooted at ``lca.infrastructure.sandbox`` or
  ``lca.infrastructure.transport``.
* ``direct_sandbox_call`` — a call of the form ``sandbox.<name>(...)``.
* ``direct_transport_call`` — a call of the form ``transport.<name>(...)``.

Only top-level attribute access on the bare names ``sandbox`` /
``transport`` is flagged; chained method calls on a locally-bound
instance are not (those are the recommended seam usage pattern).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Sequence
from dataclasses import dataclass, fields
from pathlib import Path

#: Module prefixes considered "direct L0 infra" for Bodies.
_LAYER0_SANDBOX_PREFIX: str = "lca.infrastructure.sandbox"
_LAYER0_TRANSPORT_PREFIX: str = "lca.infrastructure.transport"
_LAYER0_PREFIXES: tuple[str, ...] = (
    _LAYER0_SANDBOX_PREFIX,
    _LAYER0_TRANSPORT_PREFIX,
)

#: Bare module-style names whose attribute calls are flagged.
_BARE_MODULE_NAMES: frozenset[str] = frozenset({"sandbox", "transport"})


@dataclass(frozen=True)
class Finding:
    """One audit finding."""

    path: str
    line: int
    col: int
    kind: str
    message: str


class _DirectCommandFinder(ast.NodeVisitor):
    """Walk an AST and collect direct-L0 / sandbox / transport usages."""

    def __init__(self, source_path: str) -> None:
        self._source_path = source_path
        self.findings: list[Finding] = []

    # -- imports -----------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        """``import lca.infrastructure.sandbox[...]``."""
        for alias in node.names:
            if _starts_with_layer0_prefix(alias.name):
                self.findings.append(
                    Finding(
                        path=self._source_path,
                        line=node.lineno,
                        col=node.col_offset,
                        kind="direct_layer0_import",
                        message=f"import {alias.name}",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """``from lca.infrastructure.transport.ssh import ...``."""
        if node.level > 0:
            # Relative import — cannot be an L0 infra root reference.
            self.generic_visit(node)
            return
        module = node.module or ""
        if _starts_with_layer0_prefix(module):
            names = ", ".join(a.name for a in node.names) or "<star>"
            self.findings.append(
                Finding(
                    path=self._source_path,
                    line=node.lineno,
                    col=node.col_offset,
                    kind="direct_layer0_import",
                    message=f"from {module} import {names}",
                )
            )
        self.generic_visit(node)

    # -- calls -------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        """``sandbox.run(...)`` / ``transport.send(...)``."""
        func = node.func
        if isinstance(func, ast.Attribute):
            value = func.value
            if isinstance(value, ast.Name) and value.id in _BARE_MODULE_NAMES:
                kind = "direct_sandbox_call" if value.id == "sandbox" else "direct_transport_call"
                self.findings.append(
                    Finding(
                        path=self._source_path,
                        line=node.lineno,
                        col=node.col_offset,
                        kind=kind,
                        message=f"{value.id}.{func.attr}",
                    )
                )
        self.generic_visit(node)


def _starts_with_layer0_prefix(name: str) -> bool:
    """Return True when *name* equals or is a dotted child of an L0 prefix."""
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in _LAYER0_PREFIXES)


def _scan_python_file(path: Path) -> list[Finding]:
    """Parse *path* as Python and return direct-command findings."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        # Unreadable / unparsable files are silently skipped — the
        # audit reports what it can prove, not what it cannot read.
        return []

    finder = _DirectCommandFinder(str(path))
    finder.visit(tree)
    return finder.findings


def scan_direct_commands(roots: Sequence[Path]) -> list[Finding]:
    """Scan every ``*.py`` under each *root* for direct L0 commands.

    Args:
        roots: Directories to scan recursively. Non-existent roots are
            skipped without error so the caller can pass the canonical
            Body roots unconditionally.

    Returns:
        All findings across all roots, ordered by (path, line, col).
    """
    findings: list[Finding] = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for py_file in sorted(root_path.rglob("*.py")):
            findings.extend(_scan_python_file(py_file))
    # Stable, human-friendly ordering for the report.
    findings.sort(key=lambda f: (f.path, f.line, f.col))
    return findings


def _finding_to_dict(finding: Finding) -> dict[str, object]:
    return {f.name: getattr(finding, f.name) for f in fields(Finding)}


def format_report(
    findings: list[Finding],
    *,
    json_mode: bool = False,
) -> str:
    """Render *findings* as either JSON or a human-readable report.

    Args:
        findings: Output of :func:`scan_direct_commands`.
        json_mode: When true, emit JSON; otherwise emit a
            line-oriented human-readable report.

    Returns:
        The formatted report as a string (always terminated with a
        single newline).
    """
    if json_mode:
        payload: list[dict[str, object]] = [_finding_to_dict(f) for f in findings]
        return json.dumps(payload, indent=2, ensure_ascii=False)

    if not findings:
        return "✓ No direct sandbox/transport usage in scanned Body roots."

    lines: list[str] = []
    lines.append(f"Found {len(findings)} direct-command issue(s):")
    lines.append("")
    for finding in findings:
        lines.append(f"  {finding.path}:{finding.line}:{finding.col}")
        lines.append(f"    [{finding.kind}] {finding.message}")
    return "\n".join(lines)


#: Re-exported for convenience in CLI / script wiring.
__all__: Sequence[str] = (
    "Finding",
    "format_report",
    "scan_direct_commands",
)
