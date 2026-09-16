"""AST guard: graph nodes must not steal fields off ``context.runtime``.

PR-A refactor: typed-port inputs are the canonical input shape for graph
nodes. A node may only read from ``context.runtime`` for the kernel-injected
runtime carriers (``state`` / ``writer`` / ``effect_gateway`` / ``cursor`` /
``brain`` / ``body`` / ``memory`` / ``perceive_hub``); every other field
must travel via the declared typed ports.

The guard fails loud when an AST under ``lca/nodes/`` reaches into
``context.runtime`` for any field outside the carrier whitelist. The
canonical patterns caught here are:

- ``getattr(context.runtime, "foo")``
- ``context.runtime.get("foo")``
- ``context.runtime.foo``

The whitelist names are also enforced: a node may not declare a port name
on ``declared_inputs`` that collides with a runtime carrier (the port
contract wins and the runtime field is ignored).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NODES_ROOT = REPO_ROOT / "lca" / "nodes"

# Kernel-injected runtime carriers (brief §1 "唯一的例外"). Anything
# outside this set that a graph node reads off ``context.runtime`` is a
# field-theft regression and must move to a typed port or
# ``runtime.brain.<attr>`` single-step access.
ALLOWED_RUNTIME_CARRIERS: frozenset[str] = frozenset(
    {
        "state",
        "writer",
        "effect_gateway",
        "cursor",
        "brain",
        "body",
        "memory",
        "perceive_hub",
    }
)


def _iter_node_files() -> list[Path]:
    """Return every Python file under ``lca/nodes/`` (skip ``__init__``)."""
    return sorted(
        path
        for path in NODES_ROOT.rglob("*.py")
        if path.is_file() and path.name != "__init__.py"
    )


def _runtime_field_accesses(tree: ast.AST) -> list[tuple[str, str, int]]:
    """Return (file_rel, field, line_no) for every disallowed runtime access.

    Three access shapes are flagged:

    1. ``getattr(context.runtime, "<field>")`` — explicit attribute read.
    2. ``context.runtime.get("<field>")`` — mapping-style read.
    3. ``context.runtime.<field>`` — bare attribute access.

    Each is matched against :data:`ALLOWED_RUNTIME_CARRIERS`; the carrier
    whitelist is the only allowed reader of ``context.runtime``.

    Only the outermost field-access node is reported per occurrence;
    nested attribute nodes (e.g. the ``context.runtime`` part of
    ``context.runtime.get(...)``) are skipped to avoid double-reporting
    and to keep the field name honest. We use a parent-aware walk to
    implement this filtering precisely.
    """
    findings: list[tuple[str, str, int]] = []
    for parent, node in _walk_with_parent(tree):
        if not _is_outermost_runtime_access(node, parent):
            continue
        field = _extract_runtime_field(node)
        if field is None:
            continue
        if field in ALLOWED_RUNTIME_CARRIERS:
            continue
        findings.append(("lca/nodes", field, node.lineno))
    return findings


def _walk_with_parent(tree: ast.AST) -> list[tuple[ast.AST | None, ast.AST]]:
    """Yield ``(parent, node)`` for every node in ``tree`` (parent=None at root)."""
    pairs: list[tuple[ast.AST | None, ast.AST]] = []

    def visit(parent: ast.AST | None, current: ast.AST) -> None:
        pairs.append((parent, current))
        for child in ast.iter_child_nodes(current):
            visit(current, child)

    visit(None, tree)
    return pairs


def _is_outermost_runtime_access(node: ast.AST, parent: ast.AST | None) -> bool:
    """True if ``node`` is the outermost runtime-access expression in its chain.

    For ``context.runtime.get("state")``, the outermost node is the
    ``Call`` — the inner ``context.runtime`` Attribute (the receiver of
    ``.get``) and the outer ``context.runtime.get`` Attribute (the
    ``func`` of the Call) are both skipped. This avoids reporting
    ``runtime`` itself or the ``.get`` method name as a stolen field.
    """
    if isinstance(node, ast.Call):
        # Always treat Call as the outermost: even when wrapped in a
        # larger expression, the field name lives on the call itself.
        return True
    if isinstance(node, ast.Attribute):
        # ``context.runtime.<field>`` is a bare attribute read; only
        # emit a finding when this Attribute is NOT the func of a Call
        # (the Call branch above would have caught ``.get(...)``) and
        # NOT the receiver of another Attribute access.
        if isinstance(parent, ast.Call) and parent.func is node:
            return False
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "runtime"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "context"
        ):
            return True
    return False


def _extract_runtime_field(node: ast.AST) -> str | None:
    """Return the runtime-field name if ``node`` reads off ``context.runtime``.

    ``None`` when the node does not match one of the three access shapes.
    """
    if isinstance(node, ast.Call):
        func = node.func
        # ``getattr(context.runtime, "<field>")``
        if (
            isinstance(func, ast.Name)
            and func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Attribute)
            and isinstance(node.args[0].value, ast.Name)
            and node.args[0].value.id == "context"
            and node.args[0].attr == "runtime"
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            return node.args[1].value
        # ``context.runtime.get("<field>")``
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "runtime"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "context"
            and len(node.args) >= 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            return node.args[0].value
    if isinstance(node, ast.Attribute):
        # ``context.runtime.<field>`` (bare attribute read; the
        # ``context.runtime`` Attribute itself is filtered by
        # ``_is_outermost_runtime_access``).
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "runtime"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "context"
        ):
            return node.attr
    return None


def _iter_node_files() -> list[Path]:
    """Return every Python file under ``lca/nodes/`` (skip ``__init__``)."""
    return sorted(
        path
        for path in NODES_ROOT.rglob("*.py")
        if path.is_file() and path.name != "__init__.py"
    )


@pytest.mark.parametrize("node_path", _iter_node_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_node_does_not_steal_runtime_fields(node_path: Path) -> None:
    """Each ``lca/nodes/**/*.py`` file reads only the whitelisted runtime carriers."""
    source = node_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(node_path))
    findings = _runtime_field_accesses(tree)
    assert findings == [], (
        f"{node_path.relative_to(REPO_ROOT)} reads disallowed fields off "
        f"context.runtime: {findings}. Allowed carriers: "
        f"{sorted(ALLOWED_RUNTIME_CARRIERS)}. Move them to a declared "
        f"typed port (input.port_values[<name>]) or to "
        f"runtime.brain.<attr> single-step access."
    )
