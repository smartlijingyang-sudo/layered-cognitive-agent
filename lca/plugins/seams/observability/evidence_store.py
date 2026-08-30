"""EvidenceStore seam plugin (Tier-1) —— ADR-0065 PR-2 / L5 / L8.

声明 ``evidence_store`` + ``evidence_policy`` capability 并提供 fs 后端
默认实现。Provider 插件可以 ``ctx.require("evidence_store")`` 拿到默认
后再 ``ctx._inner.provide(...)`` 覆盖(测试场景用 in-memory 替换)。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from lca.contracts.observability.evidence import EvidencePolicy, EvidenceStore
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-evidence-store-seam",
    provides=["evidence_store", "evidence_policy"],
    implements=[EvidenceStore, EvidencePolicy],
    layer="L0",
    effects="filesystem",
    description="Provide evidence_store + evidence_policy capability seams (ADR-0065 L5 / L8).",
    test_suite="tests/test_seam_evidence_store.py::test_seam_provides_both",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability.evidence.policy import DefaultEvidencePolicy
    from lca.infrastructure.observability.evidence.store import FilesystemEvidenceStore
    from lca.infrastructure.observability.settings import ObservabilitySettings

    del config
    settings = ObservabilitySettings()
    root = Path(settings.evidence_root or "traces/evidence")
    store = FilesystemEvidenceStore(root=root)
    policy = DefaultEvidencePolicy()
    ctx.provide("evidence_store", store)
    ctx.provide("evidence_policy", policy)
