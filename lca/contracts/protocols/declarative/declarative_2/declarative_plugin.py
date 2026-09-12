"""PluginSpec / PluginManifest declarations.

ADR-0221: ``PhaseContribution`` and the ``contributes`` PluginSpec field
have been retired. Phase contributions are expressed as additional
subgraph nodes inside the corresponding phase subgraph bundle, not as
static plugin-manifest declarations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    ALLOWED_EFFECTS,
    PLUGIN_SPEC_VERSION,
    DeclarativeValidationError,
    PluginSpecKind,
    RelationType,
)

if TYPE_CHECKING:
    from lca.contracts.atoms.functional.group import FunctionalGroup


def _as_text_tuple(values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise DeclarativeValidationError("PS-001", "tuple-typed field must be sequence")
    result = []
    for item in values:
        if not isinstance(item, str):
            raise DeclarativeValidationError(
                "PS-001", f"tuple element must be str, got {type(item).__name__}"
            )
        result.append(item)
    return tuple(result)


def _require_non_empty_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DeclarativeValidationError("PS-001", f"{field} must be non-empty str")
    return value


@dataclass(frozen=True, slots=True)
class CapabilityDeclaration:
    key: str
    cardinality: str = "one"
    protocol: str = "object"
    resolution_key: str = ""
    scope: str = "profile"

    def __post_init__(self) -> None:
        _require_non_empty_text(self.key, "capability.key")
        if self.cardinality not in {"one", "optional", "many", "ordered-many"}:
            raise DeclarativeValidationError(
                "PS-001", f"cardinality must be in known set; got {self.cardinality!r}"
            )


@dataclass(frozen=True, slots=True)
class EvidenceDeclaration:
    emits: tuple[str, ...] = ()
    replay: str = "optional"

    def __post_init__(self) -> None:
        object.__setattr__(self, "emits", _as_text_tuple(self.emits))
        if self.replay not in {"required", "optional", "forbidden"}:
            raise DeclarativeValidationError(
                "PS-001", f"replay must be required/optional/forbidden; got {self.replay!r}"
            )


@dataclass(frozen=True, slots=True)
class EffectGovernanceDeclaration:
    effect_class: str
    policy: str
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if self.effect_class not in ALLOWED_EFFECTS:
            raise DeclarativeValidationError(
                "PS-006", f"effect_governance effect_class must be in ALLOWED_EFFECTS"
            )
        _require_non_empty_text(self.policy, "effect_governance.policy")


@dataclass(frozen=True, slots=True)
class LifecycleDeclaration:
    scopes: tuple[str, ...] = ()
    activation: str = "true"
    disposal: str = "required"

    def __post_init__(self) -> None:
        object.__setattr__(self, "scopes", _as_text_tuple(self.scopes))


@dataclass(frozen=True, slots=True)
class OwnershipDeclaration:
    reads: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    state_mutation: str = "forbidden"

    def __post_init__(self) -> None:
        object.__setattr__(self, "reads", _as_text_tuple(self.reads))
        object.__setattr__(self, "emits", _as_text_tuple(self.emits))
        if self.state_mutation not in {"forbidden", "scoped", "allowed"}:
            raise DeclarativeValidationError(
                "PS-001",
                f"state_mutation must be forbidden/scoped/allowed; got {self.state_mutation!r}",
            )


@dataclass(frozen=True, slots=True)
class PluginImplementation:
    module: str
    setup: str = "setup"
    factory: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.module, "implementation.module")
        _require_non_empty_text(self.setup, "implementation.setup")


@dataclass(frozen=True, slots=True)
class PluginConfiguration:
    schema: str = "builtins.dict"
    values: Mapping[str, Any] = field(default_factory=dict)
    frozen: bool = True

    def __post_init__(self) -> None:
        _require_non_empty_text(self.schema, "configuration.schema")
        if not isinstance(self.values, Mapping):
            object.__setattr__(self, "values", dict(self.values))


@dataclass(frozen=True, slots=True)
class VerificationDeclaration:
    test_suite: str
    properties: tuple[str, ...]
    fixtures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.test_suite:
            raise DeclarativeValidationError("PS-001", "verification.test_suite must be non-empty")
        if not self.properties:
            raise DeclarativeValidationError("PS-001", "verification.properties must be non-empty")
        object.__setattr__(self, "properties", _as_text_tuple(self.properties))
        object.__setattr__(self, "fixtures", _as_text_tuple(self.fixtures))


@dataclass(frozen=True, slots=True)
class PluginRelation:
    type: RelationType
    target: str
    mode: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.type, RelationType):
            object.__setattr__(self, "type", RelationType(self.type))
        if not self.target:
            raise DeclarativeValidationError("PS-003", "relation target must be non-empty")
        if self.type is RelationType.REPLACES and self.mode not in {"exclusive", "fallback"}:
            raise DeclarativeValidationError(
                "PS-001", "replaces relation mode must be exclusive or fallback"
            )


@dataclass(frozen=True, slots=True)
class PluginSpec:
    """激活插件的唯一结构化架构事实。"""

    api_version: str
    id: str
    revision: str
    kind: PluginSpecKind
    layer: str
    functional_group: str
    implementation: PluginImplementation
    configuration: PluginConfiguration
    provides: tuple[CapabilityDeclaration, ...]
    requires: tuple[CapabilityDeclaration, ...]
    effects: tuple[str, ...]
    ownership: OwnershipDeclaration
    lifecycle: LifecycleDeclaration
    relations: tuple[PluginRelation, ...]
    evidence: EvidenceDeclaration
    verification: VerificationDeclaration
    effect_governance: tuple[EffectGovernanceDeclaration, ...] = ()

    def __post_init__(self) -> None:
        if self.api_version != PLUGIN_SPEC_VERSION:
            raise DeclarativeValidationError(
                "PS-001", f"unsupported PluginSpec apiVersion: {self.api_version}"
            )
        if not self.id or not self.revision or not self.layer or not self.functional_group:
            raise DeclarativeValidationError("PS-001", "identity fields must be non-empty")
        if not isinstance(self.kind, PluginSpecKind):
            object.__setattr__(self, "kind", PluginSpecKind(self.kind))
        for effect in self.effects:
            if effect not in ALLOWED_EFFECTS:
                raise DeclarativeValidationError("PS-006", f"unsupported effect class: {effect}")
        if not self.effects:
            raise DeclarativeValidationError("PS-006", "effects.classes must be non-empty")
        if not isinstance(self.provides, tuple):
            object.__setattr__(self, "provides", tuple(self.provides))
        if not isinstance(self.requires, tuple):
            object.__setattr__(self, "requires", tuple(self.requires))
        if not isinstance(self.relations, tuple):
            object.__setattr__(self, "relations", tuple(self.relations))
        if not isinstance(self.effect_governance, tuple):
            object.__setattr__(self, "effect_governance", tuple(self.effect_governance))
        for governance in self.effect_governance:
            if not isinstance(governance, EffectGovernanceDeclaration):
                raise DeclarativeValidationError(
                    "PS-006",
                    "effect_governance entries must be EffectGovernanceDeclaration values",
                )
            if governance.effect_class not in self.effects:
                raise DeclarativeValidationError(
                    "PS-006",
                    "effect governance must refer to an effect declared by the PluginSpec",
                )


__all__ = [
    "CapabilityDeclaration",
    "EffectGovernanceDeclaration",
    "EvidenceDeclaration",
    "LifecycleDeclaration",
    "OwnershipDeclaration",
    "PluginConfiguration",
    "PluginImplementation",
    "PluginRelation",
    "PluginSpec",
    "VerificationDeclaration",
]
