"""声明式插件的稳定、可序列化 schema。

插件描述所需的 identity、capability、生命周期、证据和验证元数据均在此处定义。
运行时编译、关系解析和执行选择由 harness 拥有。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.declarative.declarative_capability import CapabilityDeclaration
from lca.contracts.protocols.declarative.declarative_common import (
    AGGREGATIONS,
    ALLOWED_EFFECTS,
    PLUGIN_SPEC_VERSION,
    ContributionRole,
    DeclarativeValidationError,
    PluginSpecKind,
    RelationType,
    SemanticPhase,
)


def _as_text_tuple(value: tuple[str, ...] | Any) -> tuple[str, ...]:
    """Normalize declaration text collections while preserving tuple identity."""
    return value if isinstance(value, tuple) else tuple(str(item) for item in value)


@dataclass(frozen=True, slots=True)
class EffectGovernanceDeclaration:
    """Plan-owned governance facts for one declared effect class."""

    effect_class: str
    requires_approval: bool = False
    requires_idempotency: bool = False

    def __post_init__(self) -> None:
        if self.effect_class not in ALLOWED_EFFECTS:
            raise DeclarativeValidationError(
                "PS-006",
                f"unsupported effect class: {self.effect_class}",
            )
        if type(self.requires_approval) is not bool:
            raise DeclarativeValidationError(
                "PS-006",
                "effect governance requires_approval must be a boolean",
            )
        if type(self.requires_idempotency) is not bool:
            raise DeclarativeValidationError(
                "PS-006",
                "effect governance requires_idempotency must be a boolean",
            )
        if self.effect_class == "none" and (self.requires_approval or self.requires_idempotency):
            raise DeclarativeValidationError(
                "PS-006",
                "effect class 'none' cannot require approval or idempotency",
            )


@dataclass(frozen=True, slots=True)
class PluginImplementation:
    module: str
    setup: str = "setup"
    factory: str = "create_executor"

    def __post_init__(self) -> None:
        if not self.module:
            raise DeclarativeValidationError("PS-001", "implementation.module must be non-empty")
        if not self.setup:
            raise DeclarativeValidationError("PS-001", "implementation.setup must be non-empty")


@dataclass(frozen=True, slots=True)
class PluginConfiguration:
    schema: str
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.schema:
            raise DeclarativeValidationError("PS-001", "configuration.schema must be non-empty")
        if not isinstance(self.values, Mapping):
            object.__setattr__(self, "values", dict(self.values))


@dataclass(frozen=True, slots=True)
class OwnershipDeclaration:
    reads: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    state_mutation: str = "forbidden"

    def __post_init__(self) -> None:
        if self.state_mutation not in {"forbidden", "reducer-only"}:
            raise DeclarativeValidationError(
                "PS-001", "ownership.state_mutation must be forbidden or reducer-only"
            )
        object.__setattr__(self, "reads", _as_text_tuple(self.reads))
        object.__setattr__(self, "emits", _as_text_tuple(self.emits))


@dataclass(frozen=True, slots=True)
class LifecycleDeclaration:
    scopes: tuple[str, ...]
    activation: str
    disposal: str

    def __post_init__(self) -> None:
        if not self.scopes:
            raise DeclarativeValidationError("PS-001", "lifecycle.scopes must be non-empty")
        if not self.activation:
            raise DeclarativeValidationError("PS-001", "lifecycle.activation must be explicit")
        if not self.disposal:
            raise DeclarativeValidationError("PS-001", "lifecycle.disposal must be explicit")
        object.__setattr__(self, "scopes", _as_text_tuple(self.scopes))


@dataclass(frozen=True, slots=True)
class EvidenceDeclaration:
    emits: tuple[str, ...]
    replay: str

    def __post_init__(self) -> None:
        if not self.replay:
            raise DeclarativeValidationError("PS-001", "evidence.replay must be explicit")
        object.__setattr__(self, "emits", _as_text_tuple(self.emits))


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
class PhaseContribution:
    phase: SemanticPhase
    role: ContributionRole
    executor: str
    output: str
    order: int | None = None
    aggregation: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.phase, SemanticPhase):
            object.__setattr__(self, "phase", SemanticPhase(self.phase))
        if not isinstance(self.role, ContributionRole):
            object.__setattr__(self, "role", ContributionRole(self.role))
        if not self.executor:
            raise DeclarativeValidationError("PS-001", "contribution.executor must be non-empty")
        if not self.output:
            raise DeclarativeValidationError("PS-001", "contribution.output must be non-empty")
        if self.role is ContributionRole.GOVERN and self.aggregation not in AGGREGATIONS:
            raise DeclarativeValidationError(
                "PS-001", "govern contribution must declare a supported aggregation"
            )


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
    contributes: tuple[PhaseContribution, ...] = ()
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
        if not isinstance(self.contributes, tuple):
            object.__setattr__(self, "contributes", tuple(self.contributes))
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
        kinds_requiring_contribution = {
            PluginSpecKind.CONTRIBUTION,
            PluginSpecKind.PHASE_EXECUTOR,
            PluginSpecKind.EFFECT_HANDLER,
            PluginSpecKind.OBSERVER,
        }
        requires_control_contribution = self.kind is PluginSpecKind.PROVIDER and self.id.startswith(
            "control."
        )
        if (
            self.kind in kinds_requiring_contribution or requires_control_contribution
        ) and not self.contributes:
            raise DeclarativeValidationError(
                "PS-001", f"{self.id or self.kind.value} requires an explicit contributes section"
            )


__all__ = [
    "CapabilityDeclaration",
    "EffectGovernanceDeclaration",
    "EvidenceDeclaration",
    "LifecycleDeclaration",
    "OwnershipDeclaration",
    "PhaseContribution",
    "PluginConfiguration",
    "PluginImplementation",
    "PluginRelation",
    "PluginSpec",
    "VerificationDeclaration",
]
