"""Audit: detect direct ``AgentState`` mutations outside the reducer.

Constitution v3 §C4 mandates that the reducer is the *sole* writer of
``AgentState``.  This module scans ``lca/layer1_cognitive/``,
``lca/layer2_runtime/`` and ``lca/layer3_agent/`` with stdlib ``ast``
(never importing the scanned modules) and reports every direct write
that bypasses the reducer.

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
    """One detected state-mutation violation.

    Attributes:
        path: Filesystem path of the offending source file (as ``str``).
        line: 1-based line number of the mutation.
        col: 0-based column offset of the mutation target.
        kind: One of ``direct_attr_assign``, ``subscript_assign``,
              ``dict_or_setattr_mutation``, ``method_call_mutation``.
        message: Human-readable description of the violation.
    """

    path: str
    line: int
    col: int
    kind: str
    message: str


# The reducer is the sole legitimate AgentState writer (C4).
# Files whose path ends with any of these suffixes are skipped.
_REDUCER_FILE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "lca/layer2_runtime/reducer.py",
    }
)

_VALID_KINDS: frozenset[str] = frozenset(
    {
        "direct_attr_assign",
        "subscript_assign",
        "dict_or_setattr_mutation",
        "method_call_mutation",
    }
)


def _is_state_ref(node: ast.AST) -> bool:
    """Return True if ``node`` is a direct reference to ``state`` or ``self.state``."""
    return (isinstance(node, ast.Name) and node.id == "state") or (
        isinstance(node, ast.Attribute)
        and node.attr == "state"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _has_state_root(node: ast.AST) -> bool:
    """Return True if ``node`` is an attribute chain rooted in ``state``/``self.state``."""
    return _is_state_ref(node) or (isinstance(node, ast.Attribute) and _has_state_root(node.value))


def _is_allowlisted(filepath: Path) -> bool:
    """Return True if ``filepath`` matches any entry in the reducer allowlist."""
    as_str = str(filepath)
    # Normalise to forward-slash suffix comparison so both
    # ``lca/layer2_runtime/reducer.py`` and ``/abs/.../lca/layer2_runtime/reducer.py`` match.
    normalised = as_str.replace("\\", "/")
    return any(normalised.endswith(suffix) for suffix in _REDUCER_FILE_ALLOWLIST)


class _StateWriterVisitor(ast.NodeVisitor):
    """AST visitor that records direct ``AgentState`` mutations."""

    def __init__(self, filepath: str) -> None:
        self._filepath = filepath
        self.findings: list[Finding] = []

    # -- visitors ---------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        """Pattern 1 (attribute assign) and pattern 3 (subscript assign)."""
        for target in node.targets:
            self._check_assign_target(target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Pattern 2 — augmented assignment (``state.x += 1``)."""
        self._check_augassign_target(node.target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Pattern 4 (dict/setattr mutation) and pattern 5 (method call mutation)."""
        func = node.func
        # Pattern 4a: ``setattr(state, ...)``
        if isinstance(func, ast.Name) and func.id == "setattr":
            if node.args and _is_state_ref(node.args[0]):
                self.findings.append(
                    Finding(
                        path=self._filepath,
                        line=node.lineno,
                        col=node.col_offset,
                        kind="dict_or_setattr_mutation",
                        message=f"setattr(state, ...) call at line {node.lineno}",
                    )
                )
        elif isinstance(func, ast.Attribute):
            # Pattern 5: ``state.append(...)`` / ``state.clear()`` / ...
            if _is_state_ref(func.value):
                self.findings.append(
                    Finding(
                        path=self._filepath,
                        line=node.lineno,
                        col=node.col_offset,
                        kind="method_call_mutation",
                        message=f"state.{func.attr}() call at line {node.lineno}",
                    )
                )
            # Pattern 4b: ``state.field.update(...)`` / ``state.field.extend(...)``
            elif _has_state_root(func.value) and not _is_state_ref(func.value):
                field_name = self._leaf_attr(func.value)
                self.findings.append(
                    Finding(
                        path=self._filepath,
                        line=node.lineno,
                        col=node.col_offset,
                        kind="dict_or_setattr_mutation",
                        message=(f"state.{field_name}.{func.attr}() call at line {node.lineno}"),
                    )
                )
        self.generic_visit(node)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _leaf_attr(node: ast.AST) -> str:
        """Return the outermost attribute name in an attribute chain."""
        if isinstance(node, ast.Attribute):
            return node.attr
        return "?"

    def _check_assign_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Attribute):
            # Pattern 1 — direct attribute assignment (incl. nested chains
            # like ``state.budget.used_steps = step``).
            if _has_state_root(target):
                self.findings.append(
                    Finding(
                        path=self._filepath,
                        line=target.lineno,
                        col=target.col_offset,
                        kind="direct_attr_assign",
                        message=f"state.{target.attr} = ... at line {target.lineno}",
                    )
                )
        elif isinstance(target, ast.Subscript):
            # Pattern 3 — ``state['key'] = ...`` (or ``self.state['k'] = ...``).
            if _is_state_ref(target.value):
                self.findings.append(
                    Finding(
                        path=self._filepath,
                        line=target.lineno,
                        col=target.col_offset,
                        kind="subscript_assign",
                        message=f"state[...] = ... at line {target.lineno}",
                    )
                )
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._check_assign_target(elt)

    def _check_augassign_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Attribute) and _has_state_root(target):
            self.findings.append(
                Finding(
                    path=self._filepath,
                    line=target.lineno,
                    col=target.col_offset,
                    kind="direct_attr_assign",
                    message=f"state.{target.attr} += ... at line {target.lineno}",
                )
            )


def scan_state_writers(roots: Sequence[Path]) -> list[Finding]:
    """Scan ``roots`` for direct ``AgentState`` mutations.

    Args:
        roots: Sequence of directory paths to walk (typically the three
            layer directories under ``lca/``). Each entry is recursively
            scanned for ``*.py`` files.

    Returns:
        Flat list of :class:`Finding` instances, ordered by file path
        then by line number.
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
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            visitor = _StateWriterVisitor(str(py_file))
            visitor.visit(tree)
            all_findings.extend(visitor.findings)

    # Stable ordering: by path, then line, then column.
    all_findings.sort(key=lambda f: (f.path, f.line, f.col))
    return all_findings


def format_report(findings: list[Finding], *, json_mode: bool = False) -> str:
    """Render ``findings`` for CLI output.

    Args:
        findings: Findings to render.
        json_mode: If ``True``, emit a JSON array; otherwise emit a
            human-readable text report.

    Returns:
        Formatted report string (always ends with a newline).
    """
    if json_mode:
        payload = [asdict(f) for f in findings]
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    if not findings:
        return "No state mutations detected.\n"

    lines = [f"Found {len(findings)} state mutation(s):", ""]
    for finding in findings:
        lines.append(
            f"{finding.path}:{finding.line}:{finding.col}: {finding.kind}: {finding.message}"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "Finding",
    "format_report",
    "scan_state_writers",
]
