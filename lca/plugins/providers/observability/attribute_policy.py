"""AttributePolicy factory plugin (Tier-2).

把 ``AttributePolicy`` 注册为 ``attribute_policy_backends`` 的 factory。
默认实现：标准 verbosity + 脱敏，与旧 ``BoundObservability.policy`` 等价。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.observability.ports import AttributePolicyBackend
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-attribute-policy-default-factory",
    requires=["attribute_policy_backends"],
    implements=[AttributePolicyBackend],
    layer="L0",
    effects="none",
    description="Register AttributePolicy factory as attribute_policy_backends['default'].",
    test_suite="tests/test_attribute_policy_plugin.py::test_provider_registers_default_factory",
    kind=PluginKind.PROVIDER,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=(
            "lca-attribute-policy-default-factory.checked",
            "lca-attribute-policy-default-factory.served",
        ),
        revision="v1",
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

    registry: NamedRegistry = ctx.require("attribute_policy_backends")

    def _make_default(
        settings: ObservabilitySettings | None = None, **_: Any
    ) -> AttributePolicyBackend:
        cfg = settings or ObservabilitySettings()
        return AttributePolicy(verbosity=cfg.verbosity, redact=cfg.redact_enabled)

    registry.register("default", _make_default)
