"""Audit direct ``AgentState`` mutations outside the reducer.

Constitution v3 §C4 mandates that the reducer is the sole writer of
``AgentState``. This module scans ``lca/layer1_cognitive/``,
``lca/layer2_runtime/`` and ``lca/layer3_agent/`` with stdlib ``ast``
(never importing the scanned modules) and reports every direct write that
bypasses the reducer.

The audit recognizes function parameters annotated as ``AgentState`` and
``self.state``. It deliberately ignores local dictionaries merely named
``state`` and read-only method calls such as ``get()``, ``lower()`` or
``snapshot()``.

Public API
----------
``scan_state_writers(roots)``
    Pure function. Input: scan roots. Output: flat ``list[Finding]``.

``format_report(findings, *, json_mode=False)``
    Render findings for CLI output (plain text or JSON).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    """One detected state-mutation violation."""

    path: str
    line: int
    col: int
    kind: str
    message: str


_REDUCER_FILE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "lca/layer2_runtime/reducer.py",
        "lca/layer1_cognitive/brain/modular_brain.py",
    }
)

_MUTATING_METHODS: frozenset[str] = frozenset(
    {
        "add",
        "append",
        "clear",
        "difference_update",
        "discard",
        "extend",
        "insert",
        "intersection_update",
        "pop",
        "remove",
        "reverse",
        "setdefault",
        "sort",
        "symmetric_difference_update",
        "update",
    }
)


def _annotation_is_agent_state(annotation: ast.expr | None) -> bool:
    """Return whether an annotation names ``AgentState`` without importing code."""
    if annotation is None:
        return False
    if isinstance(annotation, ast.Name):
        return annotation.id == "AgentState"
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == "AgentState"
    return any(
        isinstance(node, ast.Name) and node.id == "AgentState" for node in ast.walk(annotation)
    )


def _is_allowlisted(filepath: Path) -> bool:
    """Return whether ``filepath`` matches a reducer-only implementation file."""
    normalised = str(filepath).replace("\\", "/")
    return any(normalised.endswith(suffix) for suffix in _REDUCER_FILE_ALLOWLIST)


class _StateWriterVisitor(ast.NodeVisitor):
    """AST visitor that records direct writes to typed ``AgentState`` values."""

    def __init__(self, filepath: str) -> None:
        self._filepath = filepath
        self._state_scopes: list[set[str]] = []
        self.findings: list[Finding] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        names = {
            argument.arg
            for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            if _annotation_is_agent_state(argument.annotation)
        }
        if node.args.vararg is not None and _annotation_is_agent_state(node.args.vararg.annotation):
            names.add(node.args.vararg.arg)
        if node.args.kwarg is not None and _annotation_is_agent_state(node.args.kwarg.annotation):
            names.add(node.args.kwarg.arg)
        self._state_scopes.append(names)
        self.generic_visit(node)
        self._state_scopes.pop()

    def _is_state_ref(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return any(node.id in scope for scope in self._state_scopes)
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "state"
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        )

    def _has_state_root(self, node: ast.AST) -> bool:
        return self._is_state_ref(node) or (
            isinstance(node, ast.Attribute) and self._has_state_root(node.value)
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_assign_target(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_assign_target(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_augassign_target(node.target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "setattr":
            if node.args and self._is_state_ref(node.args[0]):
                self._add(node, "dict_or_setattr_mutation", "setattr(state, ...) call")
        elif isinstance(func, ast.Attribute) and func.attr in _MUTATING_METHODS:
            if self._is_state_ref(func.value):
                self._add(node, "method_call_mutation", f"state.{func.attr}() call")
            elif self._has_state_root(func.value):
                field_name = self._leaf_attr(func.value)
                self._add(
                    node,
                    "dict_or_setattr_mutation",
                    f"state.{field_name}.{func.attr}() call",
                )
        self.generic_visit(node)

    @staticmethod
    def _leaf_attr(node: ast.AST) -> str:
        if isinstance(node, ast.Attribute):
            return node.attr
        return "?"

    def _check_assign_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Attribute) and self._has_state_root(target):
            self._add(target, "direct_attr_assign", f"state.{target.attr} = ...")
        elif isinstance(target, ast.Subscript) and self._is_state_ref(target.value):
            self._add(target, "subscript_assign", "state[...] = ...")
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._check_assign_target(element)

    def _check_augassign_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Attribute) and self._has_state_root(target):
            self._add(target, "direct_attr_assign", f"state.{target.attr} += ...")
        elif isinstance(target, ast.Subscript) and self._is_state_ref(target.value):
            self._add(target, "subscript_assign", "state[...] += ...")

    def _add(self, node: ast.expr | ast.stmt, kind: str, message: str) -> None:
        self.findings.append(
            Finding(
                path=self._filepath,
                line=node.lineno,
                col=node.col_offset,
                kind=kind,
                message=f"{message} at line {node.lineno}",
            )
        )


def scan_state_writers(roots: Sequence[Path]) -> list[Finding]:
    """Scan ``roots`` for direct ``AgentState`` mutations.

    Each root is recursively scanned for Python files. Reducer implementation
    files are the sole allowlisted writer locations.
    """
    all_findings: list[Finding] = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for py_file in sorted(root_path.rglob("*.py")):
            if _is_allowlisted(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            visitor = _StateWriterVisitor(str(py_file))
            visitor.visit(tree)
            all_findings.extend(visitor.findings)
    all_findings.sort(key=lambda finding: (finding.path, finding.line, finding.col))
    return all_findings


def format_report(findings: list[Finding], *, json_mode: bool = False) -> str:
    """Render findings for CLI output (plain text or canonical JSON)."""
    if json_mode:
        return (
            json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True) + "\n"
        )
    if not findings:
        return "No state mutations detected.\n"
    lines = [f"Found {len(findings)} state mutation(s):", ""]
    lines.extend(
        f"{finding.path}:{finding.line}:{finding.col}: {finding.kind}: {finding.message}"
        for finding in findings
    )
    return "\n".join(lines) + "\n"


__all__ = ["Finding", "format_report", "scan_state_writers"]
