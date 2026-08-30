"""Validate capability declarations against the plugin manifest graph.

Every capability added to ``lca/contracts/capabilities.py`` must have:

1. a typed contract symbol advertised through ``implements``;
2. a plugin owner in the scanned ``lca/plugins`` tree; and
3. a statically inspectable capability key in the plugin declaration.

The scanner intentionally uses AST instead of importing plugin modules.  This
keeps the check deterministic and makes it safe to run before profile boot.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CAPABILITIES_FILE = REPO / "lca" / "contracts" / "capabilities.py"
PLUGINS_DIR = REPO / "lca" / "plugins"
SEAM_DIR = PLUGINS_DIR / "seam_definitions"
CONTRACTS_DIR = REPO / "lca" / "contracts"


@dataclass(frozen=True, slots=True)
class PluginDeclaration:
    """Manifest fields needed by the capability wiring check."""

    path: Path
    plugin_id: str
    provides: tuple[str, ...]
    implements: tuple[str, ...]


def _read_tree(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _capability_constants() -> dict[str, str]:
    """Resolve ``CAPABILITY.key`` expressions from the canonical key module."""
    tree = _read_tree(CAPABILITIES_FILE)
    if tree is None:
        return {}
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        value: ast.AST | None = None
        name: str | None = None
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        if name is None or not isinstance(value, ast.Call):
            continue
        function = value.func
        if not (
            isinstance(function, ast.Subscript)
            and isinstance(function.value, ast.Name)
            and function.value.id == "Capability"
        ):
            continue
        if value.args and isinstance(value.args[0], ast.Constant):
            key = value.args[0].value
            if isinstance(key, str):
                constants[name] = key
    return constants


def _string_value(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.Attribute) and node.attr == "key" and isinstance(node.value, ast.Name):
        return constants.get(node.value.id)
    return None


def _string_items(node: ast.AST, constants: dict[str, str]) -> tuple[str, ...] | None:
    scalar = _string_value(node, constants)
    if scalar is not None:
        return (scalar,)
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    values: list[str] = []
    for item in node.elts:
        value = _string_value(item, constants)
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _implements_items(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[str] = []
        for item in node.elts:
            if isinstance(item, ast.Name):
                values.append(item.id)
            elif isinstance(item, ast.Attribute):
                values.append(item.attr)
            elif isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value)
            else:
                return None
        return tuple(values)
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        return (node.attr,)
    return None


def _plugin_declarations() -> tuple[PluginDeclaration, ...]:
    """Extract all ``@plugin`` declarations, including nested seam modules."""
    constants = _capability_constants()
    declarations: list[PluginDeclaration] = []
    for path in sorted(PLUGINS_DIR.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = _read_tree(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "setup":
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Name) or decorator.func.id != "plugin":
                    continue
                fields = {
                    keyword.arg: keyword.value for keyword in decorator.keywords if keyword.arg
                }
                plugin_id = _string_value(fields.get("id", ast.Constant("")), constants)
                provides = _string_items(fields.get("provides", ast.Tuple(elts=[])), constants)
                implements = _implements_items(fields.get("implements", ast.Tuple(elts=[])))
                if plugin_id is None or provides is None or implements is None:
                    continue
                declarations.append(
                    PluginDeclaration(
                        path=path,
                        plugin_id=plugin_id,
                        provides=provides,
                        implements=implements,
                    )
                )
                break
    return tuple(declarations)


def _contract_symbols() -> frozenset[str]:
    """Return names declared by the contracts layer.

    A capability may be implemented by a Protocol or a pure contract class;
    both are valid typed manifest evidence.  Whether the symbol is a Protocol
    remains enforced by the normal type and architecture checks.
    """
    symbols: set[str] = set()
    for path in CONTRACTS_DIR.rglob("*.py"):
        tree = _read_tree(path)
        if tree is None:
            continue
        symbols.update(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    return frozenset(symbols)


def _capability_keys() -> tuple[str, ...]:
    """Read the canonical capability key literals."""
    return tuple(sorted(set(_capability_constants().values())))


def _providers_by_capability(
    declarations: tuple[PluginDeclaration, ...],
) -> dict[str, tuple[PluginDeclaration, ...]]:
    providers: dict[str, list[PluginDeclaration]] = {}
    for declaration in declarations:
        for key in declaration.provides:
            providers.setdefault(key, []).append(declaration)
    return {key: tuple(value) for key, value in providers.items()}


# These keys predate the capability-wiring gate and are covered by the legacy
# seam/provider checks.  New keys must pass the manifest-aware rules below.
_PRE_EXISTING = frozenset(
    {
        "llm",
        "tools",
        "transport",
        "skills",
        "file_store",
        "observability",
        "sandbox",
        "memory",
        "search",
        "state_store",
        "perceive",
        "gates",
        "bodies",
        "brains",
        "stop_rules",
        "hooks",
        "team_strategies",
        "run_loop_driver_registry",
        "component_registry",
        "llm_resolver",
        "safe_executor.simple",
        "middleware_registry.memory",
        "reasoner.prompt",
        "critic.simple",
        "journal_store",
        "tools.compose_service",
        "transport.compose_service",
        "composition.compose_factory",
        "event_descriptor_registry",
        "trace_inspector_tools",
        "cli_debug_command",
        "genai_semantic_mapper",
        "observability_scorer",
    }
)


def main() -> int:
    keys = _capability_keys()
    providers = _providers_by_capability(_plugin_declarations())
    contract_symbols = _contract_symbols()
    new_keys = [key for key in keys if key not in _PRE_EXISTING]
    violations: list[str] = []

    for key in new_keys:
        owners = providers.get(key, ())
        if not owners:
            violations.append(f"  - {key}: no plugin declares provides=['{key}']")
            continue
        if not any(set(owner.implements).intersection(contract_symbols) for owner in owners):
            advertised = sorted({name for owner in owners for name in owner.implements})
            violations.append(
                f"  - {key}: plugin owner has no contracts-layer implements symbol "
                f"(advertised: {advertised or ['<none>']})"
            )

    if violations:
        print("VIOLATIONS (new capability keys missing manifest wiring):")
        print("\n".join(violations))
        print(f"\nFound {len(violations)} capability keys requiring typed plugin wiring.")
        return 1

    print(f"OK: {len(new_keys)} new capability keys have typed plugin wiring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
