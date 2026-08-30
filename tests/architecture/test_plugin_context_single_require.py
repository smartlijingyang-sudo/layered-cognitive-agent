"""Architecture guard for the manifest plugin dependency-read seam.

Manifest plugins run behind ``AuditedPluginContext``.  They must use its one
public dependency-read interface, ``require``, so declaration checks, audit
records, and boot-time failures stay local to a plugin's declared interface.
Carrier-level Cordis contexts deliberately remain outside this rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

from lca.harness.plugin_api import AuditedPluginContext, PluginContext

REPO = Path(__file__).resolve().parents[2]
PLUGIN_ROOTS = (REPO / "lca" / "plugins", REPO / "gateway" / "plugins")


def _plugin_context_inject_calls(path: Path) -> list[int]:
    """Return source lines where a manifest plugin bypasses ``require``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "inject"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ctx"
    ]


def test_audited_plugin_context_exposes_one_dependency_read_interface() -> None:
    """The plugin-facing protocol must not retain the carrier compatibility alias."""
    assert "require" in PluginContext.__dict__
    assert "inject" not in PluginContext.__dict__
    assert "require" in AuditedPluginContext.__dict__
    assert "inject" not in AuditedPluginContext.__dict__


def test_manifest_plugin_modules_do_not_bypass_the_require_seam() -> None:
    """Every manifest plugin keeps dependency reads on the audited test surface."""
    violations: list[str] = []
    for root in PLUGIN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            for line in _plugin_context_inject_calls(path):
                violations.append(f"{path.relative_to(REPO)}:{line}")

    assert not violations, (
        "Manifest plugins must use ctx.require(...) for declared dependencies; "
        "ctx.inject(...) is reserved for carrier-level Cordis contexts.\n" + "\n".join(violations)
    )
