"""PR-B guard: each split think node owns one responsibility (bounded surface).

plan §3.6 requires the 4 new single-responsibility nodes to stay small in
behaviour: at most 4 methods on the executor class. A node growing past
that is re-accumulating the mixed responsibilities PR-B split out.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_NODE_FILES: tuple[str, ...] = (
    "lca/nodes/think/llm/invoke.py",
    "lca/nodes/think/llm/persist.py",
    "lca/nodes/think/budget/threshold_gate.py",
    "lca/nodes/think/context/truncate.py",
)

_MAX_EXECUTOR_METHODS = 4


def _executor_method_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Executor"):
            return sum(
                1
                for stmt in node.body
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    raise AssertionError(f"no *Executor class found in {path}")


@pytest.mark.parametrize("rel_path", _NODE_FILES)
def test_node_executor_def_count_bounded(rel_path: str) -> None:
    path = Path(rel_path)
    assert path.exists(), f"expected PR-B node file {rel_path} to exist"
    count = _executor_method_count(path)
    assert count <= _MAX_EXECUTOR_METHODS, (
        f"{rel_path}: executor defines {count} methods (> {_MAX_EXECUTOR_METHODS}); "
        "a single-responsibility node should not re-accumulate mixed jobs"
    )
