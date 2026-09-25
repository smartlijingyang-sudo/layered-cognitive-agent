"""ADR-0249: the episode path does not assign through a ``state`` name."""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FILES = (
    _ROOT / "lca/cognition/memory/govern.py",
    _ROOT / "lca/contracts/models/memory/episode.py",
    _ROOT / "lca/infrastructure/memory/dream.py",
    _ROOT / "lca/infrastructure/memory/episode_buffer.py",
)


def _targets(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.Assign):
        found: list[ast.AST] = []
        for target in node.targets:
            found.extend(_flatten(target))
        return found
    if isinstance(node, ast.AnnAssign):
        return _flatten(node.target)
    if isinstance(node, ast.AugAssign):
        return _flatten(node.target)
    return []


def _flatten(target: ast.AST) -> list[ast.AST]:
    if isinstance(target, ast.Tuple | ast.List):
        found: list[ast.AST] = []
        for elt in target.elts:
            found.extend(_flatten(elt))
        return found
    return [target]


def _writes_state_attribute(target: ast.AST) -> bool:
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "state"
    )


def test_episode_modules_do_not_assign_state_attributes() -> None:
    offenders: list[str] = []
    for path in _FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for target in _targets(node):
                if _writes_state_attribute(target):
                    offenders.append(f"{path}:{getattr(node, 'lineno', '?')}")
    assert offenders == []
