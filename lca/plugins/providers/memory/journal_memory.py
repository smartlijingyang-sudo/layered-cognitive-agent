"""MemoryJournal factory plugin (Tier-2).

把 ``RunStore`` 注册为 ``journal_backends`` 的 factory。RunStore 自身满足
``JournalBackend`` Protocol（结构化鸭子类型：write/flush/close 都在）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

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
from lca.contracts.observability.ports import JournalBackend
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-journal-memory-factory",
    requires=["journal_backends"],
    implements=[JournalBackend],
    layer="L0",
    effects="none",
    description="Register RunStore factory as journal_backends['memory'].",
    test_suite="tests/test_journal_plugin.py::test_provider_registers_memory_factory",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-journal-memory-factory.checked", "lca-journal-memory-factory.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import (
        AttributePolicy,
        NamedRegistry,
        ObservabilitySettings,
    )

    registry: NamedRegistry = ctx.require("journal_backends")

    def _make_memory(
        settings: ObservabilitySettings | None = None,
        *,
        projections: tuple[Any, ...] = (),
        policy: AttributePolicy | None = None,
        descriptor_registry: Any = None,
        **_: Any,
    ) -> JournalBackend:
        cfg = settings or ObservabilitySettings()
        pol = (
            policy
            if policy is not None
            else AttributePolicy(verbosity=cfg.verbosity, redact=cfg.redact_enabled)
        )
        from lca.infrastructure.observability.journal_backend import MemoryJournal

        return MemoryJournal(
            policy=pol,
            projections=projections,
            descriptor_registry=descriptor_registry,
        )

    registry.register("memory", _make_memory)
