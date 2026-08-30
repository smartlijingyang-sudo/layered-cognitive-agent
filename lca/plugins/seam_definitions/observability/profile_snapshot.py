"""ProfileSnapshot seam plugin (Tier-1) —— ADR-0096 MVA-3.

声明 ``profile_snapshots`` 注册中心；boot 后 ``providers/profile_snapshot/run_boot``
注入 ``RunBootSnapshot`` 实现,boot 期一次性写 ``traces/runs/<id>/profile_snapshot.json``。
plugin.inventory 不再写 journal。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-profile-snapshot-seam",
    provides=["profile_snapshots"],
    requires=[],
    layer="L0",
    effects="none",
    description="Provide the profile_snapshots registry (ADR-0096 MVA-3).",
    test_suite="tests/test_profile_snapshot_seam.py::test_profile_snapshot_seam_provides_registry",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    ctx.provide("profile_snapshots", NamedRegistry())
