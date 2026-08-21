"""Attribute policy seam plugin (Tier-1).

声明 ``attribute_policy`` 注册中心；boot 后 ``providers/attribute_policy`` 把
``AttributePolicy`` factory 注入。新增 attribute policy = 新增 provider + 注册一行。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.ports import AttributePolicyBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-attribute-policy-seam",
    provides=["attribute_policy_backends"],
    implements=[AttributePolicyBackend],
    layer="L0",
    effects="none",
    description="Provide the attribute_policy_backends seam (facade plugin-ification).",
    test_suite="tests/test_attribute_policy_plugin.py::test_seam_provides_registry",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability import NamedRegistry

    ctx.provide("attribute_policy_backends", NamedRegistry())
