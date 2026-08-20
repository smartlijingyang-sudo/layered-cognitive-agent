"""Workspace Provider plugin — Tier-2 (placeholder).

Full WorkspaceService does not yet exist in lca/layer0_infra/workspace/.
This Tier-2 stub is a safe default that registers a no-op workspace.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(
    name="lca-workspace-provider",
    requires=["workspace"],
    layer="provider",
    side_effects="none",
    policy_class="observe",
    description="Placeholder Workspace provider — real implementation deferred.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """WorkspaceService does not exist yet; deferred to follow-up."""
    pass
