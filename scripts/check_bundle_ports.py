#!/usr/bin/env python3
"""check_bundle_ports — every executor's declared_inputs must be wired by its bundle node.

ADR-0219 §5.5 puts the port contract on ``NodeExecutor.declared_inputs``, but the
runtime projection is driven by the bundle node's yaml ``inputs`` list
(``PortRegistry.build_input`` receives the compiled ``NodeIOSchema``). The two are
authored in different files and nothing tied them together, so a node could declare
a typed port, silently receive ``None`` for it, and fail soft.

That is how ``think.decision.repair`` shipped with a dead argument-schema validator:
``ThinkDecisionRepairExecutor.declared_inputs`` names ``tools``, the bundle listed
only ``[decision]``, and ``_lookup_schema`` treats a ``None`` registry as "no schema
declared" and passes every call through.

Statically, no boot and no factory resolution:

1. AST-scan ``lca/**/*.py`` for classes carrying a literal ``semantic_name`` and a
   literal ``declared_inputs`` tuple of ``PortName("...")``.
2. Scan ``bundles/**/*.yaml`` for ``nodes[]`` entries with a ``factory`` and ``inputs``.
3. For every bundle node whose ``factory`` matches a discovered ``semantic_name``,
   assert each declared input port appears in that node's ``inputs`` list.

Executors whose ``declared_inputs`` is computed rather than literal are reported as
unresolved and do not fail the check.

``BASELINE`` records the findings that predate this gate. Default mode fails on
anything outside the baseline, so a newly dropped port breaks the build at once.
Each baseline entry needs one of two verdicts before it can leave the list: the
executor reads the port from ``input.port_values`` and the bundle must wire it, or
``declared_inputs`` went stale in a refactor and the port must be deleted from the
declaration. ``--strict`` fails on the baseline too, and is the delete-when for the
list.

用法::

    uv run python scripts/check_bundle_ports.py
    uv run python scripts/check_bundle_ports.py --strict
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPO_ROOT / "lca"
BUNDLE_ROOT = REPO_ROOT / "bundles"

#: Findings that predate this gate, keyed by bundle node id.
BASELINE: dict[str, frozenset[str]] = {
    "act.fanout": frozenset({"envelopes"}),
    "act.observe.normalize": frozenset({"journal"}),
    "memory.write.dispatch": frozenset({"memory"}),
    "prompt.sections.assemble": frozenset({"prompt_template_provider"}),
    "prompt.sections.fill": frozenset({"tools_provider", "prompt_section_registry"}),
    "phase.perceive.observe": frozenset({"state"}),
    "capability.fork.dispatch": frozenset({"bindings"}),
    "phase.reflect.score": frozenset({"state", "cognitive_reflection_pipeline"}),
    "phase.remember.write": frozenset({"effect_gateway"}),
    "think.route": frozenset({"in_assembled_manifest"}),
    "llm.invoke": frozenset({"render", "tools", "state"}),
    # Listing ``tools`` here makes the boot-time plan lift reject the profile:
    # think.decision.repair is not the entry node of think.subgraph, and no
    # reachable predecessor inside that plan produces ``tools``. Seeded ports
    # are only exempt on an entry node, which is why tool.fork.dispatch gets
    # away with declaring it. ``forked_tools`` is produced by think.reason and
    # is available at this point, so that is the port to validate against.
    "think.decision.repair": frozenset({"tools"}),
}


def _literal_port_names(node: ast.expr) -> tuple[str, ...] | None:
    """Extract ``PortName("x")`` literals from a tuple/list assignment.

    Returns ``None`` when the value is not a literal sequence of PortName calls,
    so a computed contract is reported as unresolved instead of being guessed.
    """
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    names: list[str] = []
    for element in node.elts:
        if not isinstance(element, ast.Call):
            return None
        if not (isinstance(element.func, ast.Name) and element.func.id == "PortName"):
            return None
        if len(element.args) != 1 or not isinstance(element.args[0], ast.Constant):
            return None
        if not isinstance(element.args[0].value, str):
            return None
        names.append(element.args[0].value)
    return tuple(names)


def _class_contract(cls: ast.ClassDef) -> tuple[str, tuple[str, ...]] | None:
    """Return ``(semantic_name, declared_inputs)`` for a NodeExecutor class."""
    semantic_name: str | None = None
    declared: tuple[str, ...] | None = None
    for statement in cls.body:
        if not isinstance(statement, ast.AnnAssign) and not isinstance(statement, ast.Assign):
            continue
        targets = (
            [statement.target] if isinstance(statement, ast.AnnAssign) else list(statement.targets)
        )
        for target in targets:
            if not (isinstance(target, ast.Name) and statement.value is not None):
                continue
            if target.id == "semantic_name" and isinstance(statement.value, ast.Constant):
                if isinstance(statement.value.value, str):
                    semantic_name = statement.value.value
            elif target.id == "declared_inputs":
                declared = _literal_port_names(statement.value)
    if semantic_name is None:
        return None
    return semantic_name, declared or ()


def collect_executor_contracts() -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Map ``semantic_name`` to its declared input ports, plus its source location."""
    contracts: dict[str, tuple[str, ...]] = {}
    locations: dict[str, str] = {}
    unresolved: dict[str, str] = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            contract = _class_contract(node)
            if contract is None:
                continue
            name, declared = contract
            relative = path.relative_to(REPO_ROOT)
            if any(
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == "declared_inputs"
                and statement.value is not None
                and _literal_port_names(statement.value) is None
                for statement in node.body
            ):
                unresolved[name] = f"{relative}:{node.lineno}"
                continue
            contracts[name] = declared
            locations[name] = f"{relative}:{node.lineno}"
    if unresolved:
        print("unresolved declared_inputs (computed, skipped):")
        for name in sorted(unresolved):
            print(f"  {name:38s} {unresolved[name]}")
        print()
    return contracts, locations


def _port_spec_name(item: object) -> str | None:
    """Return the port name for one ``inputs`` entry.

    Bundles use two forms: a bare string, and a mapping carrying
    ``{name: <port>, required: false}`` for a port the node reads
    opportunistically. Both name a port the executor may declare.
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        name = item.get("name")
        return str(name) if isinstance(name, str) and name else None
    return None


def collect_bundle_nodes() -> list[tuple[str, str, str, list[str], int]]:
    """Yield ``(bundle_path, node_id, factory, inputs, line)`` for every bundle node."""
    rows: list[tuple[str, str, str, list[str], int]] = []
    for path in sorted(BUNDLE_ROOT.rglob("*.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"  ! {path.relative_to(REPO_ROOT)}: unparsable yaml ({exc})")
            continue
        if not isinstance(document, dict):
            continue
        nodes = document.get("nodes")
        if not isinstance(nodes, list):
            continue
        relative = str(path.relative_to(REPO_ROOT))
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            factory = node.get("factory")
            if not isinstance(factory, str) or not factory:
                continue
            raw_inputs = node.get("inputs") or []
            if isinstance(raw_inputs, list):
                inputs = [n for n in (_port_spec_name(item) for item in raw_inputs) if n]
            else:
                inputs = []
            rows.append(
                (relative, str(node.get("id") or f"nodes[{index}]"), factory, inputs, index)
            )
    return rows


def main() -> int:
    strict = "--strict" in sys.argv[1:]
    contracts, locations = collect_executor_contracts()
    rows = collect_bundle_nodes()

    new_violations: list[str] = []
    baseline_hits: list[str] = []
    stale_baseline: list[str] = []
    seen_nodes: set[str] = set()
    checked = 0
    wired: dict[str, list[str]] = defaultdict(list)

    for relative, node_id, factory, inputs, _index in rows:
        declared = contracts.get(factory)
        if declared is None:
            continue
        checked += 1
        wired[factory].append(f"{relative}#{node_id}")
        missing = frozenset(port for port in declared if port not in inputs)
        if not missing:
            seen_nodes.add(node_id)
            continue
        block = (
            f"  {relative}#{node_id}\n"
            f"    factory          : {factory}\n"
            f"    executor         : {locations.get(factory, '?')}\n"
            f"    declared_inputs  : {list(declared)}\n"
            f"    yaml inputs      : {inputs}\n"
            f"    MISSING          : {sorted(missing)}"
        )
        if node_id in BASELINE and missing <= BASELINE[node_id]:
            seen_nodes.add(node_id)
            baseline_hits.append(block)
        else:
            new_violations.append(block)

    print(f"executors with a literal port contract : {len(contracts)}")
    print(f"bundle nodes matched to an executor    : {checked}")
    print(f"distinct factories wired               : {len(wired)}")

    declared_but_unbound = sorted(set(contracts) - set(wired))
    if declared_but_unbound:
        print(f"\nexecutors never referenced by a bundle factory ({len(declared_but_unbound)}):")
        for name in declared_but_unbound:
            print(f"  {name:38s} {locations.get(name, '?')}")

    for node_id in sorted(set(BASELINE) - seen_nodes):
        stale_baseline.append(node_id)

    if new_violations:
        print(f"\nFAIL: {len(new_violations)} bundle node(s) drop a declared input port.\n")
        print("\n\n".join(new_violations))
        print(
            "\nA port the executor declares but the bundle omits arrives as None, and\n"
            "every consumer that reads it with .get() fails soft. Add the port to the\n"
            "node's yaml inputs list, or drop it from declared_inputs."
        )
        return 1

    if stale_baseline:
        print(f"\nFAIL: BASELINE entries no longer reproduce, delete them: {stale_baseline}")
        return 1

    if baseline_hits:
        if strict:
            print(f"\nFAIL (--strict): {len(baseline_hits)} baseline finding(s) remain.\n")
            print("\n\n".join(baseline_hits))
            return 1
        print(f"\nWARN: {len(baseline_hits)} baseline finding(s), each awaiting a verdict.\n")
        print("\n\n".join(baseline_hits))
        print(
            "\nWire the port or delete it from declared_inputs, then drop the node from\n"
            "BASELINE. --strict fails on these and is the delete-when for the list."
        )

    print("\nOK: no bundle node outside BASELINE drops a declared input port.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
