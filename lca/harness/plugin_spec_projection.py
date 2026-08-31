"""从规范化 Manifest 声明构造类型化 ``PluginSpec`` 的投影。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.capabilities import TOOLS
from lca.harness.plugin_manifest import EffectClass, PluginKind

if TYPE_CHECKING:
    from pydantic import BaseModel

    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        PhaseContribution,
        PluginSpec,
    )
    from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration


def native_spec_from_declaration(
    *,
    plugin_id: str,
    config_cls: type[BaseModel] | None,
    provides: tuple[str, ...],
    requires: tuple[str, ...],
    implements: tuple[str, ...],
    layer: str,
    kind: PluginKind,
    effects: frozenset[EffectClass],
    test_suite: str,
    functional_group: FunctionalGroup | None,
    module: str,
    contributes: tuple[PhaseContribution, ...] = (),
    ownership: OwnershipDeclaration | None = None,
) -> PluginSpec:
    """Create the baseline typed spec at plugin declaration time.

    Explicit ``spec=`` remains authoritative. The baseline uses only normalized
    decorator values, so the plan compiler has no compatibility projection or
    parallel source of declaration truth.
    """
    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        CapabilityDeclaration,
        EvidenceDeclaration,
        LifecycleDeclaration,
        OwnershipDeclaration,
        PluginConfiguration,
        PluginImplementation,
        PluginSpec,
        PluginSpecKind,
        VerificationDeclaration,
    )

    kind_map = {
        PluginKind.SEAM: PluginSpecKind.SEAM,
        PluginKind.PROVIDER: PluginSpecKind.PROVIDER,
        PluginKind.PRIMITIVE: PluginSpecKind.PROVIDER,
        PluginKind.COMPOSITE: PluginSpecKind.COMPOSITE,
        PluginKind.DRIVER: PluginSpecKind.DRIVER,
        PluginKind.BRIDGE: PluginSpecKind.PROVIDER,
    }
    spec_kind = kind_map[kind]
    effect_values = tuple(sorted(item.value for item in effects)) or ("none",)
    if spec_kind is PluginSpecKind.SEAM and any(item != "none" for item in effect_values):
        spec_kind = PluginSpecKind.PROVIDER
    config_name = (
        f"{config_cls.__module__}.{config_cls.__name__}" if config_cls else "builtins.dict"
    )
    return PluginSpec(
        api_version="lca/plugin-spec/v1",
        id=plugin_id,
        revision="1.0.0",
        kind=spec_kind,
        layer=layer,
        functional_group=(
            functional_group.value if functional_group else f"declared-{layer.lower()}"
        ),
        implementation=PluginImplementation(module=module, setup="setup"),
        configuration=PluginConfiguration(schema=config_name),
        provides=tuple(
            CapabilityDeclaration(
                key=key,
                cardinality="many",
                protocol="object",
                resolution_key=_resolution_key(key, implements=implements),
            )
            for key in provides
        ),
        requires=tuple(
            CapabilityDeclaration(
                key=key,
                cardinality="optional",
                protocol="object",
                resolution_key=_resolution_key(key, implements=implements),
            )
            for key in requires
        ),
        effects=effect_values,
        ownership=ownership or OwnershipDeclaration(state_mutation="forbidden"),
        lifecycle=LifecycleDeclaration(
            scopes=("profile", "run"), activation="true", disposal="required"
        ),
        relations=(),
        evidence=EvidenceDeclaration(emits=("RuntimeObserved",), replay="required"),
        verification=VerificationDeclaration(
            test_suite=test_suite or "tests", properties=("typed_plugin_spec",)
        ),
        contributes=tuple(contributes),
    )


def _resolution_key(capability: str, *, implements: tuple[str, ...]) -> str:
    """Return the Cordis key declared for one normalized capability.

    The declaration adapter owns the one compatibility translation from legacy
    plugin metadata. Every downstream plan consumer reads the resulting
    ``CapabilityDeclaration.resolution_key`` and therefore never parses tool
    or registry naming conventions while binding a runtime.
    """

    if "Tool" in implements:
        return TOOLS.key
    registry_key, separator, _selector = capability.partition("[")
    return registry_key if separator else capability
