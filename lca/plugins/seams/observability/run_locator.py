"""RunLocator seam plugin (Tier-1) —— ADR-0065 §七 / PR-5。

声明 ``run_locator`` capability;boot 后由 provider 注入 fs 默认实现。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.run_locator import RunLocator
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-run-locator-seam",
    provides=["run_locator"],
    implements=[RunLocator],
    layer="L0",
    effects="filesystem",
    description="Provide run_locator capability seam (ADR-0065 §七 / PR-5).",
    test_suite="tests/test_seam_run_locator.py::test_seam_provides_filesystem_locator",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-run-locator-seam.checked", "lca-run-locator-seam.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("run_locator",),
        emits=("run_locator.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability.run_locator_fs import FilesystemRunLocator

    del config
    root = Path("traces")
    locator = FilesystemRunLocator(root=root)
    ctx.provide("run_locator", locator)
