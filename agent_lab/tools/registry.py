"""Tool registry — runtime lookup of named Tool instances.

This is a "non-executable graph" seam: a single object that holds every
named Tool the agent loop is allowed to dispatch.  It is populated from
``tools/registry.yaml`` at boot and read by ``LcaBodyProvider`` when a
``dispatch_tool`` node asks for its tool range.

Boundary:
  - reads:  a YAML file (one file: ``tools/registry.yaml``)
  - holds:  ``dict[str, Tool]`` (real ``lca.contracts.protocols.Tool`` instances)
  - exposes: ``get(name)`` / ``names()`` / ``register()`` / ``load_from_yaml()``
  - does NOT call any Tool; it is pure data + lookup, no execution semantics.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lca.contracts.protocols import Tool


class ToolNotFoundError(KeyError):
    """A tool was requested that is not present in the registry."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:  # pragma: no cover — debug aid
        return f"tool not registered: {self.name!r}"


class ToolRegistry:
    """Named-tool lookup table.  Pure data; no Tool ever executes here."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ---- mutation ---------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """Register one Tool.  Duplicate names fail loud (per ADR-0062 §3)."""
        if not getattr(tool, "name", None):
            raise ValueError(f"tool {tool!r} has no .name attribute")
        if tool.name in self._tools:
            raise KeyError(f"tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    # ---- lookup -----------------------------------------------------------

    def get(self, name: str) -> Tool:
        """Resolve a tool by name; raise ToolNotFoundError if absent."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def contains(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    # ---- YAML load --------------------------------------------------------

    @staticmethod
    def _resolve_factory(entry: dict[str, Any]) -> Tool:
        """Resolve one YAML entry into a real Tool instance.

        Entry shape::

            ref: <module>:<Factory>            # module:Factory dotted path
            kwargs: { ... }                    # optional kwargs to the factory

        Where ``<Factory>`` is either a class implementing ``Tool`` (and we
        instantiate it) or a zero-arg factory function returning a Tool
        (e.g. ``lca.plugins.tools.bash:build_bash_tool``).
        """
        from lca.contracts.protocols import Tool  # local: avoid hard import

        ref = entry["ref"]
        kwargs = dict(entry.get("kwargs", {}) or {})
        module_name, _, factory_name = ref.partition(":")
        if not module_name or not factory_name:
            raise ValueError(f"tool factory ref must be 'module:Factory', got {ref!r}")
        module = importlib.import_module(module_name)
        factory = getattr(module, factory_name)
        instance = factory(**kwargs) if kwargs else factory()
        if not isinstance(instance, Tool):
            raise TypeError(
                f"tool factory {ref!r} returned {type(instance).__name__}, "
                "which is not a lca.contracts.protocols.Tool"
            )
        return instance

    def load_from_yaml(self, path: str | Path) -> tuple[str, ...]:
        """Load and register every tool declared in a YAML registry file.

        YAML shape::

            tools:
              - ref: lca.plugins.tools.bash:build_bash_tool
                kwargs: {}
              - ref: lca.plugins.tools.file_write:build_file_write_tool
                kwargs: {}
              - ref: agent_lab.adapters.tools.read_file:build_read_file_tool
                kwargs: {}

        Returns the names registered (for self-describe / boot log).
        """
        import yaml  # local: avoid hard import

        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "tools" not in raw:
            raise ValueError(f"tool registry YAML must have a 'tools:' list: {path}")
        registered: list[str] = []
        for entry in raw["tools"]:
            if not isinstance(entry, dict) or "ref" not in entry:
                raise ValueError(f"tool registry entry must be a {{ref: ...}} mapping: {entry!r}")
            tool = self._resolve_factory(entry)
            self.register(tool)
            registered.append(tool.name)
        return tuple(registered)


__all__ = ["ToolNotFoundError", "ToolRegistry"]
