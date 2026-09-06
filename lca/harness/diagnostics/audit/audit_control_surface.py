"""Audit declarative control contributions and reject retired raw metadata.

The executable control surface is defined by typed ``PhaseContribution`` values
that compile into ``CompiledRunPlan.control_entries``.  This scanner remains
static and import-free: it inventories declared ``control.*`` capabilities and
reports any attempt to reintroduce the retired ``control=`` manifest field.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

_CONTROL_CAPABILITY_PREFIX = "control."
_RETIRED_METADATA_KEY = "__retired_control_metadata__"


@dataclass(frozen=True)
class Finding:
    """One declarative control declaration or retired-metadata violation."""

    path: str
    line: int
    col: int
    kind: str
    message: str


class _ControlContributionFinder(ast.NodeVisitor):
    """Collect typed contribution capabilities and reject raw control metadata."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:
        is_phase_contribution = (
            isinstance(node.func, ast.Name) and node.func.id == "PhaseContribution"
        ) or (isinstance(node.func, ast.Attribute) and node.func.attr == "PhaseContribution")
        if is_phase_contribution:
            executor = next((item.value for item in node.keywords if item.arg == "executor"), None)
            if (
                isinstance(executor, ast.Constant)
                and isinstance(executor.value, str)
                and executor.value.startswith(_CONTROL_CAPABILITY_PREFIX)
            ):
                self.findings.append(
                    Finding(
                        path=self.path,
                        line=executor.lineno,
                        col=executor.col_offset,
                        kind="declarative_control_contribution",
                        message=executor.value,
                    )
                )

        for keyword in node.keywords:
            if keyword.arg == "control":
                self.findings.append(
                    Finding(
                        path=self.path,
                        line=keyword.value.lineno,
                        col=keyword.value.col_offset,
                        kind="retired_control_metadata",
                        message="@plugin control= is retired; declare typed contributes= instead",
                    )
                )
        self.generic_visit(node)


def _scan_python_file(path: Path) -> list[Finding]:
    """Scan a Python file without importing it."""

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return []

    finder = _ControlContributionFinder(str(path))
    finder.visit(tree)
    return finder.findings


def _scan_yaml_file(path: Path) -> list[Finding]:
    """Reject deprecated YAML ``control`` declarations without requiring imports."""

    try:
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (UnicodeDecodeError, yaml.YAMLError):
        return []

    findings: list[Finding] = []
    for document in documents:
        if isinstance(document, dict) and "control" in document:
            findings.append(
                Finding(
                    path=str(path),
                    line=1,
                    col=0,
                    kind="retired_control_metadata",
                    message="YAML control: is retired; use native PluginSpec contributions",
                )
            )
    return findings


def scan_control_surface(roots: Sequence[Path]) -> dict[str, list[Finding]]:
    """Inventory declarative control capabilities and report retired metadata.

    The returned dictionary is keyed by executable capability; all retired
    metadata findings are grouped under ``__retired_control_metadata__``.
    """

    findings_by_key: dict[str, list[Finding]] = {}
    for root in roots:
        if not root.exists():
            continue
        for source_file in (*root.rglob("*.py"), *root.rglob("*.yaml")):
            findings = (
                _scan_python_file(source_file)
                if source_file.suffix == ".py"
                else _scan_yaml_file(source_file)
            )
            for finding in findings:
                key = (
                    _RETIRED_METADATA_KEY
                    if finding.kind == "retired_control_metadata"
                    else finding.message
                )
                findings_by_key.setdefault(key, []).append(finding)
    return findings_by_key


def format_report(findings: dict[str, list[Finding]], *, json_mode: bool = False) -> str:
    """Format the static declarative-control audit for CLI or machine consumption."""

    if json_mode:
        import json

        return json.dumps(
            {
                key: [
                    {
                        "path": finding.path,
                        "line": finding.line,
                        "col": finding.col,
                        "kind": finding.kind,
                        "message": finding.message,
                    }
                    for finding in values
                ]
                for key, values in findings.items()
            },
            indent=2,
            ensure_ascii=False,
        )

    if not findings:
        return "No declarative control contributions found."

    lines: list[str] = []
    retired = findings.get(_RETIRED_METADATA_KEY, [])
    if retired:
        lines.append(f"Found {len(retired)} retired control metadata violation(s):")
        for finding in retired:
            lines.append(f"  {finding.path}:{finding.line}:{finding.col} {finding.message}")
        lines.append("")

    contributions = {
        key: values for key, values in findings.items() if key != _RETIRED_METADATA_KEY
    }
    if contributions:
        lines.append("Declarative control contributions:")
        for capability, values in sorted(contributions.items()):
            lines.append(f"[{capability}] ({len(values)} declaration(s))")
            for finding in values:
                lines.append(f"  {finding.path}:{finding.line}:{finding.col}")

    return "\n".join(lines)
