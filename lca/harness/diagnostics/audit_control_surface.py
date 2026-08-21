"""Audit Control Slot references in LCA plugin manifests and source code.

This module scans plugin sources, bundles, and profiles to detect:
1. Hardcoded Control Slot strings in Python files
2. Missing 'control' declarations in YAML plugin manifests

All scanning uses stdlib ast and yaml — never imports scanned modules.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

# Control Slots from ADR-0066 §二 + tracker §19 variants
KNOWN_CONTROL_SLOTS: frozenset[str] = frozenset(
    [
        "perceive.context",
        "think.guard",
        "act.authorize",
        "act.budget",
        "act.constrain",
        "act.execute",
        "remember.admit",
        "stop.decide",
        "observe.*",
        "observe.checkpoint",
        "act.safe-boundary",
    ]
)


@dataclass
class Finding:
    """A single audit finding."""

    path: str
    line: int
    col: int
    kind: str
    message: str


class _SlotFinder(ast.NodeVisitor):
    """AST visitor that finds hardcoded Control Slot strings."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        """Check string constants for Control Slot references."""
        if isinstance(node.value, str) and node.value in KNOWN_CONTROL_SLOTS:
            self.findings.append(
                Finding(
                    path=self.path,
                    line=node.lineno,
                    col=node.col_offset,
                    kind="hardcoded_slot_ref",
                    message=node.value,
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Recurse into function calls."""
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Recurse into subscript operations."""
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Recurse into attribute access."""
        self.generic_visit(node)


def _scan_python_file(path: Path) -> list[Finding]:
    """Scan a Python file for hardcoded Control Slot strings."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return []

    finder = _SlotFinder(str(path))
    finder.visit(tree)
    return finder.findings


def _scan_yaml_file(path: Path) -> list[Finding]:
    """Scan a YAML file for plugin manifests missing 'control' declarations."""
    try:
        text = path.read_text(encoding="utf-8")
        docs = list(yaml.safe_load_all(text))
    except (UnicodeDecodeError, yaml.YAMLError):
        return []

    findings: list[Finding] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        # Check if this is a plugin manifest (has 'id' and 'provides' or 'setup')
        if "id" not in doc:
            continue
        plugin_id = doc["id"]
        # Check for 'control' field
        if "control" not in doc:
            findings.append(
                Finding(
                    path=str(path),
                    line=1,  # YAML docs don't have precise line info
                    col=0,
                    kind="missing_control_field",
                    message=f"plugin {plugin_id} has no control: declaration",
                )
            )
    return findings


def scan_control_surface(
    roots: Sequence[Path],
) -> dict[str, list[Finding]]:
    """Scan roots for Control Slot references and missing declarations.

    Args:
        roots: Sequence of directories to scan (plugins/, bundles/, profiles/).

    Returns:
        Dict keyed by Control Slot name, with list of Findings.
        Special key "__missing_control__" for YAML findings.
    """
    findings_by_slot: dict[str, list[Finding]] = {}

    for root in roots:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            for finding in _scan_python_file(py_file):
                slot = finding.message
                if slot not in findings_by_slot:
                    findings_by_slot[slot] = []
                findings_by_slot[slot].append(finding)

        for yaml_file in root.rglob("*.yaml"):
            for finding in _scan_yaml_file(yaml_file):
                key = "__missing_control__"
                if key not in findings_by_slot:
                    findings_by_slot[key] = []
                findings_by_slot[key].append(finding)

    return findings_by_slot


def format_report(
    findings: dict[str, list[Finding]],
    *,
    json_mode: bool = False,
) -> str:
    """Format findings for CLI output.

    Args:
        findings: Dict from scan_control_surface().
        json_mode: If True, output JSON; otherwise human-readable text.

    Returns:
        Formatted report string.
    """
    if json_mode:
        import json

        # Convert findings to serializable format
        data = {
            slot: [
                {
                    "path": f.path,
                    "line": f.line,
                    "col": f.col,
                    "kind": f.kind,
                    "message": f.message,
                }
                for f in slot_findings
            ]
            for slot, slot_findings in findings.items()
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    # Human-readable format
    lines: list[str] = []
    total_findings = sum(len(v) for v in findings.values())
    if total_findings == 0:
        return "✓ No Control Slot issues found."

    lines.append(f"Found {total_findings} Control Slot issue(s):\n")

    for slot, slot_findings in sorted(findings.items()):
        lines.append(f"[{slot}] ({len(slot_findings)} finding(s))")
        for finding in slot_findings:
            lines.append(f"  {finding.path}:{finding.line}:{finding.col}")
            lines.append(f"    {finding.kind}: {finding.message}")
        lines.append("")

    return "\n".join(lines)
