"""Profile-selected invariant checker for governed Cordis composition."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.capabilities import COMPOSITION_INVARIANT_CHECKER
from lca.contracts.mechanisms.composition import InvariantChecker
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.providers.think.composition_composer import build_default_invariant_checker


class Config(BaseModel):
    """The standard invariant checker has no profile parameters."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-composition-invariant-default",
    provides=[COMPOSITION_INVARIANT_CHECKER.key],
    requires=[],
    implements=[InvariantChecker],
    layer="L0",
    effects="none",
    description="Provide the default invariant gate for Cordis Composer mount operations.",
    test_suite="tests/architecture/test_composition_invariant_capability.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the profile-selected composition invariant checker."""

    del config
    ctx.provide(COMPOSITION_INVARIANT_CHECKER.key, build_default_invariant_checker())


__all__ = ["Config", "setup"]
