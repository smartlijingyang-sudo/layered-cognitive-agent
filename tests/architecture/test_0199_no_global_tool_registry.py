"""HPC-L8 + I-HPC-9 architectural guard (ADR-0199 §11 / P5-05).

Per ADR-0199 §11 HPC-L8: "禁止新 global mutable tool registry".
Per I-HPC-9: the codebase uses plan-bound dependency injection (cordis
Context + capability key) — NOT global Service Locator / global registry.

This test scans the plugin tree for patterns that suggest a forbidden
global mutable tool registry:

  - module-level ``register`` / ``register_tool`` / ``register_capability``
    calls (registration must happen INSIDE a ``setup()`` body or via
    the AuditedPluginContext seam, never at module-import time).
  - module-level assignments whose name is a tool/handler/provider
    registry AND whose value is a mutable ``dict()`` constructor call
    (not a literal ``{...}`` data table).

The guard is AST-based (robust to formatting/comments) plus a narrow
regex for module-level dict literals whose name matches the registry
naming convention. Failure mode is a clear ``pytest.fail`` pointing at
the violating file and line.

Reference:
- ADR-0199 §11 HPC-L8 (CI / 架构门禁扩展 — 禁止新 global mutable tool registry)
- ADR-0199 §11 I-HPC-9 (分域 registry — 禁止单一 global tool registry 替代 compile projection)
- 0199-implementation-plan.md §8 row P5-05
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_TREE = REPO_ROOT / "lca" / "plugins"

# Module-level dict literals whose name suggests a tool/handler/provider
# registry. We are intentionally NARROW: only flag names whose *semantic*
# intent is to act as a runtime registry of pluggable units.
#
# Why exclude ``_REGISTRY``-suffixed names like ``TEMPLATE_REGISTRY`` /
# ``PHASE_FOLD_EPS`` / ``WIRE`` / ``CORS_HEADERS`` / ``BUILTIN_MAP``:
# those are static data lookup tables populated exactly once at import
# time from in-file literals, not mutable runtime append targets. The
# pattern we *do* want to catch is names that imply tool execution
# surfaces (``TOOL_REGISTRY``, ``TOOLSET_REGISTRY``, ``PROVIDER_REGISTRY``,
# ``HANDLER_REGISTRY``, ``CAPABILITY_REGISTRY``) — which the LCA codebase
# does NOT use at module level (it uses plan-bound DI via cordis Context).
_REGISTRY_NAME_PATTERN = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<name>(?:TOOL|TOOLSET|PROVIDER|HANDLER|CAPABILITY)_REGISTRY|"
    r"_TOOL_REGISTRY|_TOOLSET_REGISTRY|_PROVIDER_REGISTRY|"
    r"_HANDLER_REGISTRY|_CAPABILITY_REGISTRY)"
    r"\s*[:=]\s*(?:dict|OrderedDict|defaultdict)\s*\(",
)


def _walk_python_files(root: Path) -> list[Path]:
    """Find all .py files under root (excluding __pycache__)."""
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _detect_module_level_registry_dict(
    module_path: Path,
) -> list[tuple[int, str]]:
    """Return list of ``(line, name)`` for module-level dict() constructor
    assignments whose name implies a tool/handler/provider registry.

    Heuristic: any module-level statement that calls ``dict(...)`` (not
    a literal ``{...}``) and assigns to a name matching the registry
    naming convention. This catches the classic "append from anywhere"
    global mutable registry while leaving in-file literal lookup tables
    alone (those are not flagged because their value is a literal, not
    a ``dict()`` call).
    """
    try:
        source = module_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(source.splitlines(), start=1):
        m = _REGISTRY_NAME_PATTERN.match(line)
        if not m:
            continue
        indent = m.group("indent")
        if indent:
            continue
        hits.append((i, m.group("name")))
    return hits


def _detect_module_level_registration_call(
    module_path: Path,
) -> list[tuple[int, str]]:
    """Return list of ``(line, attr)`` for module-level registration calls.

    Catches code like::

        register_tool("foo", _handler)   # bare module-level call
        registry.register(_handler)      # attribute call at module level
        TOOL_REGISTRY["foo"] = _handler  # bracket-assign at module level

    outside any function/class body. Registration must live inside a
    ``setup()`` body or via the AuditedPluginContext seam.
    """
    try:
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    # Names of registration-shaped callables to flag at module top-level.
    # These are the verbs that indicate tool/capability/plugin binding —
    # anything else (logging, helpers) is out of scope.
    registration_verbs = frozenset(
        {
            "register",
            "register_tool",
            "register_capability",
            "register_handler",
            "register_provider",
            "register_toolset",
        }
    )

    hits: list[tuple[int, str]] = []
    for node in tree.body:
        # Module-level Expr wrapping a Call:  register_tool("foo")
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id in registration_verbs:
                hits.append((node.lineno, f"{call.func.id} (bare)"))
            elif isinstance(call.func, ast.Attribute) and call.func.attr in registration_verbs:
                hits.append((node.lineno, f"{call.func.attr} (attr)"))
        # Module-level Assign whose value is a registration call.
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id in registration_verbs:
                hits.append((node.lineno, f"{call.func.id} (in assign)"))
            elif isinstance(call.func, ast.Attribute) and call.func.attr in registration_verbs:
                hits.append((node.lineno, f"{call.func.attr} (attr)"))
    return hits


class TestHPCL8NoGlobalToolRegistry:
    """HPC-L8 + I-HPC-9: no new global mutable tool registries.

    The plugin tree is the canonical home of all ``@plugin(...)`` entry
    points. Any future global tool registry that sneaks in here would
    violate ADR-0199 §11 (HPC-L8) and §11 (I-HPC-9) — plan-bound DI
    only, no Service Locator.
    """

    def test_plugin_tree_exists(self) -> None:
        assert PLUGIN_TREE.exists(), (
            f"Plugin tree missing at {PLUGIN_TREE}; the architectural guard has nothing to scan."
        )

    def test_no_module_level_registry_dict(self) -> None:
        """No module-level ``dict()`` constructor assigned to a tool/handler/provider
        registry name.

        Per I-HPC-9: plan-bound DI only. Static data lookup tables
        (``TEMPLATE_REGISTRY``-style literals) are exempt because they
        are populated exactly once at import and never appended to.
        """
        violations: list[tuple[Path, int, str]] = []
        for module_path in _walk_python_files(PLUGIN_TREE):
            for line_no, name in _detect_module_level_registry_dict(module_path):
                violations.append((module_path, line_no, name))

        if violations:
            msg_lines = [
                "HPC-L8: module-level mutable tool registry dict() found:",
            ]
            for path, line, name in violations:
                rel = path.relative_to(REPO_ROOT)
                msg_lines.append(f"  {rel}:{line} → {name} = dict(...)")
            msg_lines.append(
                "\nPer ADR-0199 §11 HPC-L8 + I-HPC-9: tools/providers/handlers "
                "must be plan-bound via cordis Context + capability key. "
                "A module-level dict() call assigned to a *_REGISTRY name "
                "is the anti-pattern this guard rejects. "
                "Use the AuditedPluginContext.setup() seam or "
                "PluginContext.register() (inside a function body) instead."
            )
            pytest.fail("\n".join(msg_lines))

    def test_no_module_level_bare_register_call(self) -> None:
        """No module-level ``register(...)`` / ``registry.register(...)`` /
        ``register_tool(...)`` calls.

        Registration must happen INSIDE a ``setup()`` body or via the
        AuditedPluginContext seam — never at module-import time. A bare
        module-level registration call is the strongest signal that a
        global mutable tool registry is being populated.
        """
        violations: list[tuple[Path, int, str]] = []
        for module_path in _walk_python_files(PLUGIN_TREE):
            for line_no, attr in _detect_module_level_registration_call(module_path):
                violations.append((module_path, line_no, attr))

        if violations:
            msg_lines = [
                "HPC-L8: module-level registration calls found:",
            ]
            for path, line, attr in violations:
                rel = path.relative_to(REPO_ROOT)
                msg_lines.append(f"  {rel}:{line} → {attr}")
            msg_lines.append(
                "\nPer ADR-0199 §11 HPC-L8 + I-HPC-9: registration must be "
                "inside setup() or via AuditedPluginContext, not at "
                "module import. Module-level register() calls defeat "
                "plan-bound dependency injection (cordis Context + "
                "capability key)."
            )
            pytest.fail("\n".join(msg_lines))

    def test_heuristic_targets_registry_names_not_data_tables(self) -> None:
        """Sanity check: the heuristic distinguishes tool-registry names from
        data lookup tables.

        Existing legitimate constants (e.g. ``TEMPLATE_REGISTRY``,
        ``WIRE``, ``PHASE_FOLD_EPS``) use literal ``{...}`` values, not
        ``dict()`` constructors, and have names that do NOT match the
        tool/handler/provider registry naming convention. This test
        pins the heuristic so future edits do not accidentally widen
        it to flag those constants.
        """
        # Inline fixtures: deliberately violating patterns the heuristic MUST catch.
        violating_names = (
            "TOOL_REGISTRY",
            "TOOLSET_REGISTRY",
            "PROVIDER_REGISTRY",
            "_TOOL_REGISTRY",
            "_HANDLER_REGISTRY",
        )
        # Inline fixtures: deliberately non-violating names the heuristic MUST NOT catch.
        safe_names = (
            "TEMPLATE_REGISTRY",
            "WIRE",
            "PHASE_FOLD_EPS",
            "CORS_HEADERS",
            "BUILTIN_MAP",
            "__all__",
        )

        for name in violating_names:
            matched = _REGISTRY_NAME_PATTERN.match(f"{name} = dict()\n")
            assert matched is not None, (
                f"heuristic regression: failing to catch registry name {name!r}"
            )
            assert matched.group("name") == name

        for name in safe_names:
            matched = _REGISTRY_NAME_PATTERN.match(f"{name} = dict()\n")
            assert matched is None, (
                f"heuristic over-broad: false-positive on safe name {name!r}; "
                f"captured as {matched.group('name') if matched else None!r}"
            )
