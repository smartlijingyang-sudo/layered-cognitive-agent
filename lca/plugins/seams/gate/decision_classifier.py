"""DecisionClassifier Seam Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-decision-classifier-seam",
    provides=["decision_classifier"],
    requires=[],
    implements=["DecisionClassifier"],
    layer="L1",
    effects="none",
    kind=PluginKind.SEAM,
    description="Provide the DecisionClassifier Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.decision_classifier import DefaultDecisionClassifier

    ctx.provide("decision_classifier", DefaultDecisionClassifier())


__all__ = ["setup"]
