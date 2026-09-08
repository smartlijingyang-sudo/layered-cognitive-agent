"""Node ABC + registry.

A node is the smallest possible ant:
  execute(node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]

No control flow, no nested business. Just config -> action.

Nodes self-describe via @node(...) decorator (see nodes/manifest.py),
which populates NodeManifest alongside the class registration.
"""

from __future__ import annotations

from typing import Any

from agent_lab.graph.spec import InfoNode
from agent_lab.primitives.artifact import Artifact


class Node:
    """Base class. Subclasses override execute() with config-driven behavior."""

    name: str = "base"
    _manifest: Any = None  # populated by @node(...) decorator

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        raise NotImplementedError


_REGISTRY: dict[str, type[Node]] = {}


class NodeRegistry:
    @staticmethod
    def get(name: str) -> type[Node]:
        if name not in _REGISTRY:
            raise KeyError(f"node factory not registered: {name}")
        return _REGISTRY[name]

    @staticmethod
    def known() -> list[str]:
        return sorted(_REGISTRY.keys())

    @staticmethod
    def describe(name: str) -> Any:
        """Return the NodeManifest for a registered node. Lazy import to avoid cycles."""
        from agent_lab.nodes.manifest import _ManifestStore

        return _ManifestStore.get(name)

    @staticmethod
    def describe_all() -> dict[str, Any]:
        """Return all registered NodeManifests keyed by node id."""
        from agent_lab.nodes.manifest import _ManifestStore

        return _ManifestStore.all()


def register(cls: type[Node]) -> type[Node]:
    if not cls.name or cls.name == "base":
        raise ValueError(f"node class {cls!r} must set a unique name")
    if cls.name in _REGISTRY:
        raise ValueError(f"duplicate node factory name: {cls.name}")
    _REGISTRY[cls.name] = cls
    return cls


def invoke(node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
    """Runtime entry: look up factory by name, call execute."""
    factory = NodeRegistry.get(node.factory)
    inst = factory()
    return inst.execute(node, inputs)
