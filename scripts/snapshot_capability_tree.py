#!/usr/bin/env python3
"""Capability Tree Snapshot — ADR-0076 / W0 baseline.

Statically parse ``@plugin`` decorators and output the active structured
capability tree for the default profile. This is the W0 baseline:

- Parse all ``lca/plugins/**/*.py`` modules for ``@plugin`` metadata
- Retain only plugins activated by the selected profile in the capability tree
- Classify each plugin into one of the six planes (ADR-0076 §一)
- Map capability owners from the same resolved profile used by production compilation
- Read declarative control contributions, phase executors, effect/delta handlers
- Reuse the production compiled-plan ``plan_ref`` for the profile
- Output human-readable and JSON formats

The ``plan_ref`` is obtained from the production compiled plan, so the
snapshot cannot silently diverge from the capability, scope, or declarative
control inputs used at runtime.

The snapshot still scans every plugin module for the capability inventory, but
an unbundled plugin must not change the identity of a profile that cannot load
it. Active plugin membership is resolved through the same profile resolver used
by production plan compilation.

Usage:
    uv run python scripts/snapshot_capability_tree.py
    uv run python scripts/snapshot_capability_tree.py --json
    uv run python scripts/snapshot_capability_tree.py --profile profiles/web-standard.yaml
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.harness.profile.resolve import ResolvedProfile

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
PLUGINS_DIR = REPO / "lca" / "plugins"
DEFAULT_PROFILE = "profiles/web-standard.yaml"

# ── Six-plane classification (ADR-0076 §一) ─────────────────────────
# Plane assignment is determined by ``layer`` + ``kind`` + ``provides/requires``
# + module path. The mapping is deterministic and exhaustive.

_PLANE_RULES: list[tuple[str, dict[str, object]]] = [
    # Evidence:横切平面 — observability seam + evidence providers (check FIRST)
    (
        "evidence",
        {
            "layers": {"L0", "L1", "L2", "L3"},
            "module_patterns": [
                r"^lca/plugins/seams/observability/",
                r"^lca/plugins/providers/observability/",
                r"^lca/plugins/providers/journal/fact_store_memory",
                r"^lca/plugins/providers/memory/journal_memory",
                # Learning plugins consume completed-run evidence and produce
                # candidates/decisions; they remain cross-cutting rather than
                # introducing an ungoverned seventh runtime plane.
                r"^lca/plugins/(skill|insight|profile|learning)/",
            ],
            "kind": None,
        },
    ),
    # Constitution Kernel: contracts + runtime + phase graph
    (
        "constitution",
        {
            "layers": {"L0", "L1", "L2"},
            "module_patterns": [
                r"^lca/contracts/",
                r"^lca/runtime/",
                r"^lca/plugins/runtime/",
                r"^lca/plugins/phase_graph/",
                r"^lca/plugins/phase_edges/",
                r"^lca/plugins/phase_policies/",
                r"^lca/plugins/phase_topology/",
            ],
            "kind": None,
        },
    ),
    # Governance: control contributions
    (
        "governance",
        {
            "layers": {"L1", "L2"},
            "module_patterns": [r"^lca/plugins/control_contributions/"],
            "kind": None,
        },
    ),
    # Cognitive: brain, reasoner, critic, perceive, sensors, memory, think, gates, collaboration
    (
        "cognitive",
        {
            "layers": {"L0", "L1", "L2"},
            "module_patterns": [
                r"^lca/plugins/(brain|reasoner|critic|synthesizer|perceive|sensors|memory|think|gates|collaboration|state)/",
                r"^lca/cognition/",
            ],
            "kind": None,
        },
    ),
    # Execution: body, tools
    (
        "execution",
        {
            "layers": {"L1", "L2"},
            "module_patterns": [
                r"^lca/plugins/body/",
                r"^lca/plugins/tools/",
            ],
            "kind": None,
        },
    ),
    # Organization: strategies, roles, loop_drivers, composer, team_lead, modes + L3/L4
    (
        "organization",
        {
            "layers": {"L0", "L1", "L2", "L3", "L4"},
            "module_patterns": [
                r"^lca/plugins/(strategies|roles|loop_drivers|composer|team_lead|modes|phase_graph)/",
                r"^lca/plugins/run_loop_driver_registry\.py",
                r"^lca/agent/",
                r"^lca/application/",
                r"^gateway/",
            ],
            "kind": None,
        },
    ),
    # Infrastructure: everything else in seams, providers, compose, factories, bundles
    (
        "infrastructure",
        {
            "layers": {"L0", "L1", "L2", "L3", "L4"},
            "module_patterns": [
                r"^lca/plugins/seams/",
                r"^lca/plugins/providers/",
                r"^lca.plugins.factories/",
                r"^lca/plugins/bundles/",
            ],
            "kind": None,
        },
    ),
]


def _classify_plane(module: str, layer: str, kind: str) -> str:
    """Classify a plugin into one of the six planes (ADR-0076 §一).

    Falls back to ``"unknown"`` if no rule matches.
    """
    for plane, rule in _PLANE_RULES:
        layers: set[str] = rule.get("layers", set())  # type: ignore[assignment]
        module_patterns: list[str] = rule.get("module_patterns", [])  # type: ignore[assignment]
        kinds: set[str] | None = rule.get("kind")  # type: ignore[assignment]

        if (
            layer not in layers
            or (kinds is not None and kind not in kinds)
            or (module_patterns and not any(re.search(pat, module) for pat in module_patterns))
        ):
            continue
        return plane
    return "unknown"


def _normalize_enum_value(value: str | None) -> str | None:
    """Normalize enum references like 'PluginKind.PRIMITIVE' -> 'primitive'.

    Extracts the enum member name and lowercases it.
    Returns None if input is None.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value).lower()
    if "." in value:
        # Extract member name: "PluginKind.PRIMITIVE" -> "PRIMITIVE" -> "primitive"
        return value.split(".")[-1].lower()
    return value.lower()


# ── AST parsing ───────────────────────────────────────────────────────


@dataclass
class PluginManifest:
    """Static metadata extracted from a ``@plugin`` decorator."""

    id: str
    module: str
    layer: str
    kind: str
    provides: tuple[str, ...]
    requires: tuple[str, ...]
    implements: tuple[str, ...]
    effects: tuple[str, ...]
    functional_group: str | None
    description: str
    test_suite: str | None
    plane: str


def _parse_plugin_decorator(tree: ast.Module, module_path: str) -> PluginManifest | None:
    """Extract plugin metadata from ``@plugin(...)`` decorator."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "setup":
            continue
        # Look for @plugin(...) decorator
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not isinstance(func, ast.Name) or func.id != "plugin":
                continue
            # Extract kwargs
            kwargs: dict[str, object] = {}
            for kw in dec.keywords:
                if kw.arg is None:
                    continue
                key = kw.arg
                # Extract string literals
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    kwargs[key] = kw.value.value
                # Extract list/tuple of strings
                elif isinstance(kw.value, (ast.List, ast.Tuple)):
                    items: list[str] = []
                    for elt in kw.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            items.append(elt.value)
                        else:
                            items.append(ast.unparse(elt))
                    kwargs[key] = tuple(items)
                # Extract enum or other
                else:
                    kwargs[key] = ast.unparse(kw.value)

            plugin_id = kwargs.get("id", "")
            if not plugin_id:
                # Legacy: name= instead of id=
                plugin_id = kwargs.get("name", "")
            if not plugin_id:
                continue

            layer = kwargs.get("layer", "L0")
            kind = kwargs.get("kind", "primitive")
            # Normalize kind: handle enum references like "PluginKind.PRIMITIVE" -> "primitive"
            if isinstance(kind, str) and "." in kind:
                kind = kind.split(".")[-1].lower()
            elif isinstance(kind, str):
                kind = kind.lower()

            # Normalize effects: handle enum references like "EffectClass.NONE" -> "none"
            effects = kwargs.get("effects", ())
            if isinstance(effects, tuple):
                normalized_effects = []
                for effect in effects:
                    if isinstance(effect, str) and "." in effect:
                        normalized_effects.append(effect.split(".")[-1].lower())
                    elif isinstance(effect, str):
                        normalized_effects.append(effect.lower())
                    else:
                        normalized_effects.append(str(effect))
                effects = tuple(normalized_effects)

            # Normalize functional_group: handle enum references like "FunctionalGroup.G0" -> "G0"
            functional_group = kwargs.get("functional_group")
            if isinstance(functional_group, str) and "." in functional_group:
                functional_group = functional_group.split(".")[-1]

            provides = kwargs.get("provides", ())
            requires = kwargs.get("requires", ())
            implements = kwargs.get("implements", ())
            description = kwargs.get("description", "")
            test_suite = kwargs.get("test_suite")

            # Normalize to tuples
            if isinstance(provides, str):
                provides = (provides,)
            if isinstance(requires, str):
                requires = (requires,)
            if isinstance(implements, str):
                implements = (implements,)
            if isinstance(effects, str):
                effects = (effects,)

            plane = _classify_plane(module_path, layer, kind)

            return PluginManifest(
                id=plugin_id,
                module=module_path,
                layer=layer,
                kind=kind,
                provides=tuple(provides),
                requires=tuple(requires),
                implements=tuple(implements),
                effects=tuple(effects),
                functional_group=functional_group,
                description=description,
                test_suite=test_suite,
                plane=plane,
            )
    return None


def _scan_plugins() -> list[PluginManifest]:
    """Scan all ``lca/plugins/**/*.py`` for ``@plugin`` decorators."""
    manifests: list[PluginManifest] = []
    for py in sorted(PLUGINS_DIR.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        rel = str(py.relative_to(REPO))
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        manifest = _parse_plugin_decorator(tree, rel)
        if manifest:
            manifests.append(manifest)
    return manifests


# ── Capability mapping ────────────────────────────────────────────────


@dataclass
class CapabilityTree:
    """Structured capability tree for a profile."""

    plan_ref: str
    profile: str
    bundles: list[str]
    plugins: list[PluginManifest]
    capability_owners: dict[str, str]  # capability_key → plugin_id
    declarative_control_contributions: dict[str, list[str]]  # capability → [phase, ...]
    phase_executors: list[str]  # plugin_ids
    effect_handlers: list[str]  # plugin_ids
    delta_handlers: list[str]  # plugin_ids
    plane_summary: dict[str, int]  # plane → count
    fallback_allowlist: list[dict[str, str]]


def _resolve_profile(profile: str) -> ResolvedProfile:
    """Resolve one profile through the production compilation seam.

    The snapshot intentionally keeps AST parsing for the repository-wide
    inventory, but active membership, bundle expansion, patches, disabled
    entries, and unique capability ownership are production facts. Delegating
    them here prevents the diagnostic script from maintaining a second, looser
    bundle parser with different semantics.
    """
    from lca.harness.profile.resolve import resolve_profile

    path = Path(profile)
    return resolve_profile(path if path.is_absolute() else REPO / path)


def _module_source(module: str) -> Path:
    """Resolve an importable module name to its source file."""
    relative = Path(*module.split("."))
    module_file = REPO / relative.with_suffix(".py")
    if module_file.exists():
        return module_file
    package_init = REPO / relative / "__init__.py"
    return package_init


def _manifest_from_module(plugin_id: str, module: str) -> PluginManifest:
    """Parse an active module missed by the plugin-directory scan."""
    source = _module_source(module)
    if not source.exists():
        raise RuntimeError(f"active plugin module source not found: {module}")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    manifest = _parse_plugin_decorator(tree, module)
    if manifest is None or manifest.id != plugin_id:
        raise RuntimeError(f"active plugin manifest not statically discoverable: {plugin_id}")
    return manifest


def _build_capability_tree(profile: str) -> CapabilityTree:
    """Build the active capability tree for a profile."""
    scanned_plugins = _scan_plugins()
    resolved = _resolve_profile(profile)
    bundles = list(resolved.bundles)
    active_plugins = {
        plugin.id: plugin.module for plugin in resolved.plugins if not plugin.disabled
    }
    scanned_by_id = {plugin.id: plugin for plugin in scanned_plugins}
    plugins = [
        scanned_by_id.get(plugin_id) or _manifest_from_module(plugin_id, module)
        for plugin_id, module in sorted(active_plugins.items())
    ]

    # ``resolve_profile`` has already rejected duplicate native capability entries.
    # The snapshot therefore reads the same PluginSpec-derived ownership directory
    # as production compilation instead of reinterpreting decorator metadata.
    capability_owners = {
        capability: plugin.id
        for plugin in sorted(resolved.plugins, key=lambda item: item.id)
        if not plugin.disabled
        for capability in plugin.definition.provided_capability_keys
    }

    from lca.harness.plan import compiled_run_plan_ref
    from lca.harness.profile.plan_compiler import compile_plan

    compiled_plan = compile_plan(resolved)
    declarative_control_contributions: dict[str, list[str]] = {}
    for entry in compiled_plan.control_entries:
        declarative_control_contributions.setdefault(entry.executor_capability, []).append(
            entry.phase.value
        )

    # Phase executors: plugins in phase_executors/ directory
    phase_executors = [p.id for p in plugins if "phase_graph/" in p.module]

    # Effect/Delta handlers: plugins providing these capabilities
    effect_handlers = [
        p.id for p in plugins if "effect_handler" in p.provides or "effect_handlers" in p.provides
    ]
    delta_handlers = [
        p.id for p in plugins if "delta_handler" in p.provides or "delta_handlers" in p.provides
    ]

    # Plane summary
    plane_summary: dict[str, int] = {}
    for plugin in plugins:
        plane_summary[plugin.plane] = plane_summary.get(plugin.plane, 0) + 1

    # Fallback allowlist (W0 §任务: allowlist with reason, scope, removal_target)
    fallback_allowlist = _load_fallback_allowlist()

    plan_ref = compiled_run_plan_ref(compiled_plan)

    return CapabilityTree(
        plan_ref=plan_ref,
        profile=profile,
        bundles=bundles,
        plugins=plugins,
        capability_owners=capability_owners,
        declarative_control_contributions=declarative_control_contributions,
        phase_executors=phase_executors,
        effect_handlers=effect_handlers,
        delta_handlers=delta_handlers,
        plane_summary=plane_summary,
        fallback_allowlist=fallback_allowlist,
    )


# ── Fallback allowlist (W0 §任务) ────────────────────────────────────


def _load_fallback_allowlist() -> list[dict[str, str]]:
    """Load the fallback/direct-construction allowlist.

    Each entry has:
    - ``location``: file:line or module path
    - ``kind``: direct_construction | module_fallback | hardcoded_default
    - ``reason``: why this fallback exists
    - ``scope``: test | production | both
    - ``removal_target``: ADR or W-phase that will remove it
    """
    # 生产运行时只接受完整 binding；fixture 默认值被封装在显式的
    # ``build_fixture_cognitive_runtime`` adapter 内，而非生产 capability 图。
    # 因此当前没有需要由 capability snapshot 追踪的生产或跨路径 fallback。
    return []


# ── Output formatting ─────────────────────────────────────────────────


def _format_human_readable(tree: CapabilityTree) -> str:
    """Format the capability tree for human consumption."""
    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("Capability Tree Snapshot")
    lines.append("=" * 80)
    lines.append(f"profile:       {tree.profile}")
    lines.append(f"plan_ref:      {tree.plan_ref}")
    lines.append(f"bundles:       {len(tree.bundles)}")
    lines.append(f"plugins:       {len(tree.plugins)}")
    lines.append("")

    # Plane summary
    lines.append("─── Six-Plane Summary (ADR-0076 §一) ─────────────────────────────────────")
    for plane in [
        "constitution",
        "infrastructure",
        "cognitive",
        "governance",
        "execution",
        "organization",
        "evidence",
        "unknown",
    ]:
        count = tree.plane_summary.get(plane, 0)
        if count > 0:
            lines.append(f"  {plane:20s} {count:3d} plugins")
    lines.append("")

    # Capability owners
    lines.append("─── Capability Owners (production-resolved provides) ─────────────────────")
    for cap, owner in sorted(tree.capability_owners.items()):
        lines.append(f"  {cap:40s} → {owner}")
    lines.append("")

    # Declarative control contributions from the production compiled plan.
    if tree.declarative_control_contributions:
        lines.append(
            "─── Declarative Control Contributions (CompiledRunPlan) ─────────────────────"
        )
        for capability, phases in sorted(tree.declarative_control_contributions.items()):
            lines.append(f"  {capability:40s} ← {', '.join(phases)}")
        lines.append("")

    # Phase executors
    if tree.phase_executors:
        lines.append("─── Phase Executors ──────────────────────────────────────────────────────")
        for pid in sorted(tree.phase_executors):
            lines.append(f"  {pid}")
        lines.append("")

    # Effect/Delta handlers
    if tree.effect_handlers or tree.delta_handlers:
        lines.append("─── Effect / Delta Handlers ────────────────────────────────────────────────")
        if tree.effect_handlers:
            lines.append(f"  effect_handlers:  {', '.join(sorted(tree.effect_handlers))}")
        if tree.delta_handlers:
            lines.append(f"  delta_handlers:   {', '.join(sorted(tree.delta_handlers))}")
        lines.append("")

    # Fallback allowlist
    if tree.fallback_allowlist:
        lines.append("─── Fallback Allowlist (W0 §任务) ─────────────────────────────────────────")
        for entry in tree.fallback_allowlist:
            lines.append(f"  {entry['location']}")
            lines.append(f"    kind: {entry['kind']}")
            lines.append(f"    scope: {entry['scope']}")
            lines.append(f"    removal: {entry['removal_target']}")
            lines.append(f"    reason: {entry['reason']}")
        lines.append("")

    # Plugin list
    lines.append("─── Plugin List ────────────────────────────────────────────────────────────")
    for plugin in sorted(tree.plugins, key=lambda p: p.id):
        lines.append(f"  {plugin.id}")
        lines.append(f"    module: {plugin.module}")
        lines.append(f"    layer: {plugin.layer}, kind: {plugin.kind}, plane: {plugin.plane}")
        if plugin.provides:
            lines.append(f"    provides: {', '.join(plugin.provides)}")
        if plugin.requires:
            lines.append(f"    requires: {', '.join(plugin.requires)}")
        if plugin.functional_group:
            lines.append(f"    functional_group: {plugin.functional_group}")
        lines.append("")

    return "\n".join(lines)


def _format_json(tree: CapabilityTree) -> str:
    """Format the capability tree as JSON."""
    data = {
        "plan_ref": tree.plan_ref,
        "profile": tree.profile,
        "bundles": tree.bundles,
        "plugin_count": len(tree.plugins),
        "capability_owners": tree.capability_owners,
        "declarative_control_contributions": tree.declarative_control_contributions,
        "phase_executors": sorted(tree.phase_executors),
        "effect_handlers": sorted(tree.effect_handlers),
        "delta_handlers": sorted(tree.delta_handlers),
        "plane_summary": tree.plane_summary,
        "fallback_allowlist": tree.fallback_allowlist,
        "plugins": [
            {
                "id": p.id,
                "module": p.module,
                "layer": p.layer,
                "kind": p.kind,
                "provides": list(p.provides),
                "requires": list(p.requires),
                "implements": list(p.implements),
                "effects": list(p.effects),
                "functional_group": p.functional_group,
                "plane": p.plane,
                "description": p.description,
            }
            for p in sorted(tree.plugins, key=lambda x: x.id)
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capability Tree Snapshot — ADR-0076 / W0 baseline"
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"Profile YAML path (default: {DEFAULT_PROFILE})",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument(
        "--plan-ref-only",
        action="store_true",
        help="Output only the plan_ref hash",
    )
    args = parser.parse_args()

    tree = _build_capability_tree(args.profile)

    if args.plan_ref_only:
        print(tree.plan_ref)
        return 0

    if args.json:
        print(_format_json(tree))
    else:
        print(_format_human_readable(tree))

    return 0


if __name__ == "__main__":
    sys.exit(main())
