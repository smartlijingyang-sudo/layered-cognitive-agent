"""Audit residual hook-mounting patterns that PR-7 (CommandEnvelope 收口) retires.

This module scans layer 1-4 sources to detect:
1. ``hooks.trigger(...)`` calls
2. ``middleware_bag.<anything>`` attribute access
3. ``_emit(...)`` calls or ``_emit`` attribute access (vestige)
4. ``register_hook(...)`` / ``attach_hook(...)`` / ``subscribe(...)`` calls

All scanning uses stdlib ``ast`` — never imports scanned modules.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# Allowlist: these files legitimately hold _emit / middleware_bag (own impl).
_ALLOWLIST_BASENAMES: frozenset[str] = frozenset(
    [
        "event_bus.py",
        "hook_registry.py",
    ]
)

# Legacy hook-attach function names (flagged only when called).
_LEGACY_HOOK_ATTACH_NAMES: frozenset[str] = frozenset(
    [
        "register_hook",
        "attach_hook",
        "subscribe",
    ]
)


@dataclass(frozen=True, slots=True)
class Finding:
    """A single audit finding."""

    path: str
    line: int
    col: int
    kind: str
    message: str


class _HookAttachFinder(ast.NodeVisitor):
    """AST visitor that finds residual hook-mounting patterns."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._assign_target_ids: set[int] = set()

    # ------------------------------------------------------------------
    # Assign-target tracking (for _emit heuristic)
    # ------------------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        """Mark assignment targets so we skip ``self._emit = {}``."""
        for target in node.targets:
            self._collect_assign_ids(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Mark annotated assignment targets."""
        if node.target is not None:
            self._collect_assign_ids(node.target)
        self.generic_visit(node)

    def _collect_assign_ids(self, node: ast.AST) -> None:
        """Recursively collect IDs of assignment targets."""
        self._assign_target_ids.add(id(node))
        if isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                self._collect_assign_ids(elt)

    # ------------------------------------------------------------------
    # Pattern detection
    # ------------------------------------------------------------------

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Detect attribute-based patterns."""
        if id(node) not in self._assign_target_ids:
            # Pattern 2: middleware_bag.<anything>
            if isinstance(node.value, ast.Name) and node.value.id == "middleware_bag":
                self._add_finding(
                    node,
                    "middleware_bag_attr",
                    f"middleware_bag.{node.attr}",
                )

            # Pattern 3: _emit as attribute (but not in assign target)
            if node.attr == "_emit":
                self._add_finding(node, "legacy_underscore_emit", "_emit")

            # Pattern 1: hooks.trigger (attribute access or call)
            if (
                node.attr == "trigger"
                and isinstance(node.value, ast.Name)
                and node.value.id == "hooks"
            ):
                self._add_finding(node, "hooks_trigger_call", "hooks.trigger")

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Detect Name-based patterns."""
        if id(node) not in self._assign_target_ids and node.id == "_emit":
            # Pattern 3: _emit as bare Name
            self._add_finding(node, "legacy_underscore_emit", "_emit")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Detect call-based patterns."""
        func = node.func

        # Pattern 4: register_hook/attach_hook/subscribe as bare name call
        if isinstance(func, ast.Name) and func.id in _LEGACY_HOOK_ATTACH_NAMES:
            self._add_finding(node, "legacy_hook_attach", func.id)

        # Pattern 4: obj.register_hook/attach_hook/subscribe as call
        elif isinstance(func, ast.Attribute) and func.attr in _LEGACY_HOOK_ATTACH_NAMES:
            self._add_finding(node, "legacy_hook_attach", func.attr)

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_finding(self, node: ast.AST, kind: str, message: str) -> None:
        """Add a finding for the given AST node."""
        self.findings.append(
            Finding(
                path=self.path,
                line=node.lineno,
                col=node.col_offset,
                kind=kind,
                message=message,
            )
        )


def _scan_file(path: Path) -> list[Finding]:
    """Scan a single Python file for residual hook-mounting patterns."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return []

    finder = _HookAttachFinder(str(path))
    finder.visit(tree)
    return finder.findings


def scan_hook_attach(roots: Sequence[Path]) -> list[Finding]:
    """Scan roots for residual hook-mounting patterns.

    Args:
        roots: Sequence of directories to scan (layer1/2/3/4).

    Returns:
        List of Finding instances for detected patterns.
    """
    findings: list[Finding] = []

    for root in roots:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            # Skip allowlisted files
            if py_file.name in _ALLOWLIST_BASENAMES:
                continue
            findings.extend(_scan_file(py_file))

    return findings


def format_report(
    findings: list[Finding],
    *,
    json_mode: bool = False,
) -> str:
    """Format findings for CLI output.

    Args:
        findings: List of Finding instances from scan_hook_attach().
        json_mode: If True, output JSON; otherwise human-readable text.

    Returns:
        Formatted report string.
    """
    if json_mode:
        data = [
            {
                "path": f.path,
                "line": f.line,
                "col": f.col,
                "kind": f.kind,
                "message": f.message,
            }
            for f in findings
        ]
        return json.dumps(data, indent=2, ensure_ascii=False)

    # Human-readable format
    if not findings:
        return "✓ No residual hook-mounting patterns found."

    lines: list[str] = []
    lines.append(f"Found {len(findings)} residual hook-mounting pattern(s):\n")

    # Group by kind
    by_kind: dict[str, list[Finding]] = {}
    for finding in findings:
        by_kind.setdefault(finding.kind, []).append(finding)

    for kind in sorted(by_kind.keys()):
        kind_findings = by_kind[kind]
        lines.append(f"[{kind}] ({len(kind_findings)} finding(s))")
        for finding in kind_findings:
            lines.append(f"  {finding.path}:{finding.line}:{finding.col}")
            lines.append(f"    {finding.message}")
        lines.append("")

    return "\n".join(lines)
