"""Pure graph algorithms used by declarative plan validation."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence

from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseEdge, PhaseNode


def reachable(entry: str, outgoing: Mapping[str, Sequence[PhaseEdge]]) -> set[str]:
    visited: set[str] = set()
    todo: deque[str] = deque([entry])
    while todo:
        current = todo.popleft()
        if current in visited:
            continue
        visited.add(current)
        todo.extend(edge.target for edge in outgoing.get(current, ()))
    return visited


def has_path_between_any(
    sources: Sequence[str], targets: Sequence[str], outgoing: Mapping[str, Sequence[PhaseEdge]]
) -> bool:
    target_set = set(targets)
    return any(bool(reachable(source, outgoing) & target_set) for source in sources)


def strongly_connected_components(
    nodes: Mapping[str, PhaseNode], outgoing: Mapping[str, Sequence[PhaseEdge]]
) -> tuple[tuple[str, ...], ...]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node_id: str) -> None:
        nonlocal index
        indices[node_id] = index
        lowlinks[node_id] = index
        index += 1
        stack.append(node_id)
        on_stack.add(node_id)
        for edge in outgoing.get(node_id, ()):
            target = edge.target
            if target not in nodes:
                continue
            if target not in indices:
                visit(target)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[target])
            elif target in on_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indices[target])
        if lowlinks[node_id] == indices[node_id]:
            component: list[str] = []
            while stack:
                target = stack.pop()
                on_stack.discard(target)
                component.append(target)
                if target == node_id:
                    break
            components.append(tuple(component))

    for node_id in nodes:
        if node_id not in indices:
            visit(node_id)
    return tuple(components)


def has_directed_cycle(adjacency: Mapping[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        try:
            return any(visit(target) for target in adjacency.get(node, set()))
        finally:
            visiting.discard(node)
            visited.add(node)

    return any(visit(node) for node in adjacency)


__all__ = [
    "has_directed_cycle",
    "has_path_between_any",
    "reachable",
    "strongly_connected_components",
]
