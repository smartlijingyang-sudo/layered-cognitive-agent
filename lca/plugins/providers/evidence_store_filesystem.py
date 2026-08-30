"""EvidenceStore fs override factory (Tier-2) —— ADR-0065 PR-2.

测试场景用 InMemoryContentAddressableStore 替换默认 fs 后端。生产环境
直接用 seam 提供的默认 fs 实现,不需要本 plugin 介入。

本 plugin 走 ctx.require() 拿默认 fs,然后用 in-memory CAS 实现替换它,
方便单元测试跑得快且不留 fs 副作用。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.evidence import EvidenceStore
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-evidence-store-inmemory-override",
    requires=["evidence_store"],
    implements=[EvidenceStore],
    layer="L0",
    effects="none",
    description="Test-only: replace fs backend with in-memory CAS via ctx._inner.provide.",
    test_suite="tests/test_evidence_store_plugin.py::test_provider_overrides_with_inmemory",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """No-op 默认行为 —— 不在生产挂载;测试用 ``register_override()`` 手工替换。"""
    del ctx
    del config
