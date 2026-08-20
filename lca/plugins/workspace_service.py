"""Workspace Service Definition plugin — Tier-1 (minimal stub)."""

from __future__ import annotations

from lca.plugins._cordis_adapter import plugin


class WorkspaceService:
    """Minimal stub — full WorkspaceService deferred to follow-up.

    Holds a registry of workspace providers (currently empty).
    """

    def __init__(self) -> None:
        self._providers: dict[str, object] = {}
        self._active: str | None = None

    def register(self, name: str, provider: object, *, activate: bool = False) -> None:
        self._providers[name] = provider
        if activate or self._active is None:
            self._active = name

    def current(self) -> object | None:
        if self._active is None:
            return None
        return self._providers.get(self._active)


@plugin(
    name="lca-workspace-service",
    provides=["workspace"],
    layer="service",
    side_effects="none",
    policy_class="control",
    description="Minimal WorkspaceService stub — full implementation deferred.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx, config) -> None:
    ctx.provide("workspace", WorkspaceService())
