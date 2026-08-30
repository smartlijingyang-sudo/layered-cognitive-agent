"""Seam declaration for the remember_effects extension point."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-remember-effects-seam",
    provides=["remember_effects"],
    requires=[],
    implements=["RememberEffectsProvider"],
    layer="L1",
    effects="none",
    description="Effect seam for the 'remember' cognitive step.",
    test_suite="tests/test_plugin_alignment.py::test_seam_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    pass


__all__ = ["setup"]
