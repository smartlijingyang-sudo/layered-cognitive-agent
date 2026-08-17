"""tools seam Definition — owns ctx.tools.

Mirrors DSH ``core/tools``: a registry of tool factories. Each factory
``bind(s)``s a run's bindings (plane / file_store / sandbox / workspace) into
a concrete ``Tool`` — the DSH ``ToolFactory.bind`` pattern. Consumers
(loop / body) receive the forked per-run registry, never a process-global
tool table.

Providers register factories via ``register_factory``; ``fork_for_run``
materializes them for one run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, TypeVar

from lca.contracts.protocols import Tool, ToolRegistry

T = TypeVar("T", bound=Tool)


class ToolFactory(Generic[T]):
    """A tool factory bound to run bindings (DSH ``ToolFactory.bind``)."""

    name: str
    description: str

    def bind(self, run: Any) -> T | None:
        """Materialize a concrete tool for one run, or None to skip."""
        raise NotImplementedError


_Factory = Callable[[Any], Tool | list[Tool] | None]


class ToolsService(ToolRegistry):
    """Service Definition：工具工厂注册表 + 每 Run 实例化。

    与 DSH 对齐：``register_factory`` 是唯一的 provider 挂载点；
    ``fork_for_run`` 对每个工厂 bind 出一份只含本 run 实例的注册表。
    禁止在 bind 之外调用 resolve_machine() / resolve_sandbox()。
    """

    def __init__(self) -> None:
        self._factories: dict[str, _Factory] = {}
        self._tools: dict[str, Tool] = {}

    def register_factory(self, name: str, factory: _Factory) -> Callable[[], None]:
        """Register a tool factory. Returns its disposer."""
        if name in self._factories:
            raise KeyError(f"tools: factory {name!r} already registered")
        self._factories[name] = factory
        disposed = False

        def disposer() -> None:
            nonlocal disposed
            if disposed:
                return
            disposed = True
            self._factories.pop(name, None)
            self._tools.pop(name, None)

        return disposer

    def register(self, tool: Tool) -> None:
        """Legacy path: register a pre-built tool instance directly."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def fork_for_run(self, run: Any) -> ToolsService:
        """Fork a per-run registry: bind every factory against *run*.

        The forked registry holds only this run's concrete instances. A
        factory may return a single ``Tool``, a list of tools, or None.
        """
        forked = ToolsService()
        for name, factory in self._factories.items():
            bound = factory(run)
            if bound is None:
                continue
            if isinstance(bound, list):
                for tool in bound:
                    forked._tools[f"{name}:{tool.name}"] = tool
            else:
                forked._tools[name] = bound
        forked._tools.update(self._tools)
        return forked

    def names(self) -> list[str]:
        return sorted(set(self._factories) | set(self._tools))

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())
