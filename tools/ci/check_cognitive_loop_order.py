#!/usr/bin/env python3
"""CI 15.4: verify the declarative C1 phase order.

The legacy ``CognitiveRuntime._loop`` is intentionally absent.  The order is
validated at the declarative boundary: the canonical phase enum order and the
phase-graph compiler's ``for phase in SemanticPhase`` projection.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_FILE = ROOT / "lca" / "runtime" / "runtime_loop.py"
SEMANTIC_PHASE_CONTRACT_FILE = ROOT / "lca" / "contracts" / "protocols" / "declarative_common.py"
PHASE_GRAPH_COMPILER_FILE = ROOT / "lca" / "harness" / "declarative" / "phase_graph_compiler.py"
EXPECTED_PHASES = (
    "perceive",
    "think",
    "act",
    "reflect",
    "remember",
    "stop",
)


def _semantic_phase_order(path: Path) -> tuple[str, ...]:
    """Read the canonical enum order from the typed contract."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "SemanticPhase":
            continue
        values: list[str] = []
        for member in node.body:
            if not isinstance(member, ast.Assign):
                continue
            if len(member.targets) != 1 or not isinstance(member.targets[0], ast.Name):
                continue
            value = member.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                values.append(value.value)
        return tuple(values)
    raise ValueError("SemanticPhase enum not found")


def _has_legacy_loop(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_loop"
        for node in ast.walk(tree)
    )


def _has_phase_iteration(path: Path) -> bool:
    """Accept explicit loops and equivalent comprehension projections over the enum."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, (ast.For, ast.comprehension))
        and isinstance(node.iter, ast.Name)
        and node.iter.id == "SemanticPhase"
        for node in ast.walk(tree)
    )


def main() -> int:
    if _has_legacy_loop(RUNTIME_FILE):
        print("FAIL: legacy CognitiveRuntime._loop is still present")
        return 1
    try:
        phases = _semantic_phase_order(SEMANTIC_PHASE_CONTRACT_FILE)
    except (OSError, SyntaxError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    if phases != EXPECTED_PHASES:
        print(f"FAIL: declarative phase order = {phases}")
        return 1
    if not _has_phase_iteration(PHASE_GRAPH_COMPILER_FILE):
        print("FAIL: phase-graph compiler does not iterate the canonical SemanticPhase order")
        return 1
    print(f"OK: declarative cognitive loop order = {' → '.join(phases)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
