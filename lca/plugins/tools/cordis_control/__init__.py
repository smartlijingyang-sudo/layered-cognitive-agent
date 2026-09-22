"""Cordis Creator control Tool plugin and its profile-selected factory.

The concrete ``cordis_control`` Tool needs a run-scoped Composer, so it cannot be
materialized with the global tools registry.  This module exposes the narrow
``cordis_control_tool_factory`` capability instead.  A mode adapter consumes the
factory only after it has selected a Creator role profile and materialized the
profile's generic tool set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.capabilities import CORDIS_CONTROL_TOOL_FACTORY
from lca.contracts.protocols import Tool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.composition.cordis_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
from lca.plugins.tools.cordis_control.tool import (
    ALLOWED_ACTIONS,
    IDENTIFIER,
    MANIFEST,
    CordisControlTool,
    build_cordis_control_tool,
)

if TYPE_CHECKING:
    from cordis import Context


class CordisControlToolFactoryProtocol(Protocol):
    """Build one Creator control Tool with profile-owned authorization."""

    def create(self, *, scope: Context | None, actor_role: str) -> Tool: ...


@dataclass(frozen=True, slots=True)
class CordisControlToolFactory:
    """Default factory for the Composer-bound Creator control tool.

    The plugin configuration owns the maximum caller grant.  The factory does
    not choose a role, tool set, or Composer implementation; those decisions
    remain respectively with the role capability, the generic tools capability,
    and the run-scoped ``CordisComposer`` (constructed inline post-PR-C).
    """

    caller_grant: tuple[str, ...]

    def create(self, *, scope: Context | None, actor_role: str) -> Tool:
        """Build the tool with a ``CordisComposer`` constructed inline.

        PR-C: the Composer factory is no longer a runtime-bound capability;
        the cordis_control factory constructs :class:`CordisComposer`
        directly at the assembly root, with the default invariant checker.
        """

        composer = CordisComposer(
            scope, invariant_checker=build_default_invariant_checker()
        )
        return build_cordis_control_tool(
            composer=composer,
            caller_grant=self.caller_grant,
            actor_role=actor_role,
        )


class Config(BaseModel):
    """Creator control factory configuration declared by the owning bundle."""

    model_config = ConfigDict(extra="forbid")
    caller_grant: tuple[str, ...] = Field(default_factory=tuple)


@plugin(
    id="lca-tool-cordis-control",
    provides=[CORDIS_CONTROL_TOOL_FACTORY.key],
    requires=[],
    implements=["CordisControlToolFactory"],
    layer="L1",
    effects="world",
    description="Profile-selected factory for the Composer-bound cordis_control Tool.",
    test_suite="tests/test_cordis_creator_e2e.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the configured factory without constructing a run-scoped tool."""

    ctx.provide(
        CORDIS_CONTROL_TOOL_FACTORY.key,
        CordisControlToolFactory(caller_grant=tuple(config.caller_grant)),
    )


__all__ = [
    "ALLOWED_ACTIONS",
    "IDENTIFIER",
    "MANIFEST",
    "Config",
    "CordisControlTool",
    "CordisControlToolFactory",
    "CordisControlToolFactoryProtocol",
    "build_cordis_control_tool",
]
