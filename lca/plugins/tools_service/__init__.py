"""Tools service plugin — mounts the ``tools`` capability Definition.

Service Definition role (DSH ``core/tools`` mirror): owns the tool-factory
registry. The default G2A tool factory is registered here; consumers fork a
per-run registry via ``fork_for_run``.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.tools.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("tools",),
)

name = "lca.tools.service"
provides = "tools"


def _g2a_factory(bindings: Any) -> Any:
    """Bind the default G2A chat tools against a run's bindings.

    ``bindings`` is a ``PlaneBindings`` (or None for ambient). Returns a
    list of concrete ``Tool`` instances — consumed by ``fork_for_run``.
    """
    from lca.layer0_infra.tools.default_set import build_default_tools

    plane = bindings if hasattr(bindings, "primary") else None
    return build_default_tools(bindings=plane)


def apply(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.tools import ToolsService

    service = ToolsService()

    def _factory(run: Any) -> Any:
        bindings = getattr(run, "plane", None) or getattr(run, "bindings", None)
        return _g2a_factory(bindings)

    disposer = service.register_factory("g2a", _factory)
    ctx.effect(lambda: disposer, "ctx.register(tools.factory=g2a)")
    ctx.mount("tools", service)
