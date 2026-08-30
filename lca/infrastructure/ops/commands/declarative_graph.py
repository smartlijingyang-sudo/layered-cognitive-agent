"""Graph rendering and trusted-kernel auditing for declarative plans."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from lca.harness.profile.plan_compiler import compile_plan, explain_compile_plan
from lca.harness.profile.resolve import resolve_profile


def explain_declarative_plan(profile: Path) -> dict[str, Any]:
    """Return the complete plan provenance projection for a profile."""
    return explain_compile_plan(compile_plan(resolve_profile(profile)))


def render_declarative_graph(profile: Path) -> str:
    """Render capability, phase, relation, and replacement data as Mermaid."""
    plan = compile_plan(resolve_profile(profile))
    lines = ["flowchart LR"]

    if plan.phase_graph:
        lines.append("  subgraph phase_graph[Phase Graph]")
        for node in plan.phase_graph.nodes:
            node_id = _mermaid_id("phase", node.id)
            label = f"{node.semantic_phase.value}\\n{node.id}\\nmax={node.max_visits}"
            if node.terminal:
                label += "\\nterminal"
            lines.append(f"    {node_id}{_mermaid_label(label)}")
        for edge in plan.phase_graph.edges:
            source = _mermaid_id("phase", edge.source)
            target = _mermaid_id("phase", edge.target)
            edge_label = edge.when
            if edge.loop is not None:
                edge_label = (
                    f"{edge_label}\\nloop≤{edge.loop.max_iterations}, budget={edge.loop.budget}"
                )
            lines.append(f"    {source} -->|{_mermaid_text(edge_label)}| {target}")
        lines.append("  end")

    lines.append("  subgraph capability_graph[Capability Graph]")
    for binding in plan.capability_bindings:
        capability_id = _mermaid_id("cap", binding.capability)
        provider_id = _mermaid_id("plugin", binding.provider)
        lines.append(f"    {provider_id}{_mermaid_label(binding.provider)}")
        lines.append(f"    {capability_id}{_mermaid_label(binding.capability)}")
        lines.append(f"    {provider_id} -. provides .-> {capability_id}")
    lines.append("  end")

    if plan.plugin_specs:
        lines.append("  subgraph relation_graph[Plugin Relations]")
        known_plugin_ids = {spec.id for spec in plan.plugin_specs}
        for spec in plan.plugin_specs:
            source_id = _mermaid_id("plugin", spec.id)
            lines.append(f"    {source_id}{_mermaid_label(spec.id)}")
            for relation in spec.relations:
                target_id = (
                    _mermaid_id("plugin", relation.target)
                    if relation.target in known_plugin_ids
                    else _mermaid_id("ref", relation.target)
                )
                if relation.target not in known_plugin_ids:
                    lines.append(f"    {target_id}{_mermaid_label(relation.target)}")
                relation_label = relation.type.value
                if relation.mode:
                    relation_label += f" ({relation.mode})"
                lines.append(f"    {source_id} -. {_mermaid_text(relation_label)} .-> {target_id}")
        lines.append("  end")

    for decision in plan.replacement_map:
        winner = _mermaid_id("plugin", decision.winner)
        target = _mermaid_id("plugin", decision.target)
        lines.append(f"  {winner} -. replaces ({_mermaid_text(decision.mode)}) .-> {target}")
    return "\n".join(lines)


def _mermaid_id(prefix: str, value: str) -> str:
    safe = "".join(character if character.isalnum() else "_" for character in value)
    return f"{prefix}_{safe}"


def _mermaid_label(value: str) -> str:
    escaped = value.replace('"', "'").replace("\n", "<br/>")
    return f'["{escaped}"]'


def _mermaid_text(value: str) -> str:
    return value.replace("|", "/").replace("\n", "<br/>")


def audit_declarative_boundaries(root: Path) -> dict[str, Any]:
    """Reject implementation-identity dispatch in MTK and GraphAssembler."""
    files = (
        root / "lca/contracts/protocols/declarative_phase_graph.py",
        root / "lca/harness/declarative/compile/assembler.py",
        root / "lca/harness/declarative/execute/interpreter.py",
    )
    violations: list[dict[str, Any]] = []
    forbidden = {"simple", "default"}
    for path in files:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                for operand in operands:
                    if (
                        isinstance(operand, ast.Constant)
                        and isinstance(operand.value, str)
                        and (operand.value in forbidden or operand.value.startswith("plugin."))
                    ):
                        violations.append(
                            {
                                "path": str(path.relative_to(root)),
                                "line": node.lineno,
                                "message": "identity-based dispatch in trusted kernel",
                            }
                        )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "type"
            ):
                violations.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": node.lineno,
                        "message": "type-based dispatch in trusted kernel",
                    }
                )
    return {
        "audit": "declarative-boundaries",
        "scanned": [str(path.relative_to(root)) for path in files],
        "violations": violations,
        "valid": not violations,
    }


__all__ = [
    "audit_declarative_boundaries",
    "explain_declarative_plan",
    "render_declarative_graph",
]
