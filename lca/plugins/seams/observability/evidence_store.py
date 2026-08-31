"""EvidenceStore seam plugin (Tier-1) —— ADR-0065 PR-2 / L5 / L8.

声明 ``evidence_store`` + ``evidence_policy`` capability 并提供 fs 后端
默认实现。Provider 插件可以 ``ctx.require("evidence_store")`` 拿到默认
后再 ``ctx._inner.provide(...)`` 覆盖(测试场景用 in-memory 替换)。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.observability.evidence import EvidencePolicy, EvidenceStore
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
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
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=("lca-evidence-store-seam.checked", "lca-evidence-store-seam.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("evidence_policy", "evidence_store"),
        emits=("evidence_store.checked", "evidence_policy.checked"),
        state_mutation="forbidden",
    ),
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
