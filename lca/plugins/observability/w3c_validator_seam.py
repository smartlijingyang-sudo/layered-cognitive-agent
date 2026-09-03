"""W3C trace context validator seam plugin (Tier-1) —— ADR-0065 PR-7。

声明 ``w3c_trace_context_validator`` capability;boot 后由 provider 注入
默认 ``DefaultW3CValidator``。
"""

from __future__ import annotations

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
from lca.contracts.observability.w3c_trace_context import W3CTraceContextValidator
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-w3c-validator-seam",
    provides=["w3c_trace_context_validator"],
    implements=[W3CTraceContextValidator],
    layer="L0",
    effects="none",
    description="Provide W3C trace context validator (ADR-0065 §八 / PR-7).",
    test_suite="tests/test_seam_w3c_validator.py::test_seam_provides_default_validator",
    kind=PluginKind.SEAM,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("context.read",)),
        observability=EvidenceContract(
            descriptors=("lca-w3c-validator-seam.checked", "lca-w3c-validator-seam.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("w3c_trace_context_validator",),
        emits=("w3c_trace_context_validator.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability.events.w3c_validator import DefaultW3CValidator

    del config
    ctx.provide("w3c_trace_context_validator", DefaultW3CValidator())
