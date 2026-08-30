"""ArtifactClosure Seam Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-artifact-closure-seam",
    provides=["artifact_closure"],
    requires=[],
    implements=["ArtifactClosure"],
    layer="L2",
    effects="none",
    kind=PluginKind.SEAM,
    description="Provide the ArtifactClosure Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.journal.artifact_closure import DefaultArtifactClosure

    ctx.provide("artifact_closure", DefaultArtifactClosure())


__all__ = ["setup"]
