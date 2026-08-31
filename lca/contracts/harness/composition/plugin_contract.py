"""PluginContract 9 段契约（ADR-0069 §六 + tracker §12 + ADR-0110）。

PluginContract 是 plugin 作者的 typed section（ADR-0069 §六原是**可选并存**；
ADR-0110 D1 将其升级为插件侧**唯一合约面**，``functional_group=`` 与
``logic_address=`` 在 ``@plugin(...)`` 装饰器中退化为 alias 键。

9 段：

1. ``identity`` — PluginIdentity（id / version / owner）
2. ``architecture`` — ArchitectureContract（group / role / control slots）
3. ``capabilities`` — CapabilityContract（provides / requires / effect classes）
4. ``ownership`` — OwnershipContract（reads / emits / state authority）
5. ``authority`` — AuthorityContract（grant / risk / approval requirements）
6. ``lifecycle`` — LifecycleContract（allowed scopes / lease / dispose）
7. ``observability`` — EvidenceContract（descriptors / privacy / replay）
8. ``verification`` — VerificationContract（schemas / fixtures / property tests）
9. ``contribution`` — 可选的静态补充说明；不参与运行计划编译。可执行控制
   仅由原生 ``PluginSpec.contributes`` 表达。

注意：``PluginContract`` 是 **协议**（不是强制门禁）。PluginManifest
可填可空；空 ``PluginContract()`` 等价于"作者未声明"。

ADR-0015 contracts 纯类型契约：所有派生值通过 module-level 函数访问。
ADR-0110 PR-A：本模块新增 ``compose_plugin_contract`` / ``logic_address_to_plugin_contract`` /
``contract_snapshot_for_meta``，作为 ``@plugin(...)`` 装饰器 3 入口
归一到 canonical PluginContract 的唯一 seam。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.control_slot import ControlSlot, validate_slot_iterable
from lca.contracts.atoms.functional_group import (
    FunctionalGroup,
    parse_functional_group,
)
from lca.contracts.atoms.scope import Scope, parse_scope

if TYPE_CHECKING:
    from lca.contracts.protocols.composition.logic_address import LogicAddress

# ── Section dataclasses (all Optional / default-empty) ──────────────


@dataclass(frozen=True, slots=True)
class PluginIdentity:
    """plugin 身份元数据。"""

    id: str = ""
    version: str = ""
    owner: str = ""  # team / person / role


@dataclass(frozen=True, slots=True)
class ArchitectureContract:
    """静态架构归属：群 / role / control slots，不参与运行计划编译。"""

    group: FunctionalGroup | None = None
    role: str = ""
    control_slots: tuple[ControlSlot, ...] = ()

    def __post_init__(self) -> None:
        if self.group is not None and not isinstance(self.group, FunctionalGroup):
            object.__setattr__(self, "group", parse_functional_group(self.group))
        if not isinstance(self.control_slots, tuple):
            object.__setattr__(self, "control_slots", validate_slot_iterable(self.control_slots))


@dataclass(frozen=True, slots=True)
class CapabilityContract:
    """capability 声明：provides / requires / effect classes。"""

    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    effect_classes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OwnershipContract:
    """读写 / 事件发射 / 状态 authority。"""

    reads: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    state_authority: bool = False  # 是否允许写 AgentState（默认 False = 守门人）


@dataclass(frozen=True, slots=True)
class AuthorityContract:
    """grant / risk / approval 要求。"""

    grants: tuple[str, ...] = ()
    risk_level: str = ""  # "low" / "medium" / "high" / "critical" / ""
    requires_approval: bool = False


@dataclass(frozen=True, slots=True)
class LifecycleContract:
    """生命周期：allowed scopes / lease / dispose。"""

    allowed_scopes: tuple[Scope, ...] = ()
    lease_seconds: int | None = None  # None = no lease / persistent
    dispose_strategy: str = ""  # "graceful" / "force" / "noop"

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_scopes, tuple):
            scopes: list[Scope] = []
            for s in self.allowed_scopes:
                scopes.append(s if isinstance(s, Scope) else parse_scope(s))
            object.__setattr__(self, "allowed_scopes", tuple(scopes))


@dataclass(frozen=True, slots=True)
class EvidenceContract:
    """可观测 / 证据 contract。"""

    descriptors: tuple[str, ...] = ()  # Journal catalog EventDescriptor names
    privacy_class: str = ""  # "public" / "internal" / "sensitive" / "secret"
    replay_safe: bool = True


@dataclass(frozen=True, slots=True)
class VerificationContract:
    """验证 / 测试 contract。"""

    schemas: tuple[str, ...] = ()  # jsonschema / pydantic model refs
    fixtures: tuple[str, ...] = ()
    property_tests: tuple[str, ...] = ()
    test_suite: str = ""


# ── PluginContract root ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PluginContract:
    """PluginContract 9 段 root（ADR-0069 §六）。

    全部字段 optional；缺失段不阻断 plugin 加载。``contribution`` 与
    ``architecture.control_slots`` 仅用于静态架构说明；它们不会进入
    ``CompiledRunPlan``，也不会影响控制执行。

    派生值见 module-level 函数：

    - ``is_plugin_contract_empty(c)`` — 9 段是否全部默认
    - ``plugin_contract_control_slots(c)`` — 从 architecture.control_slots 取
    - ``plugin_contract_functional_group(c)`` — 从 architecture.group 取
    """

    identity: PluginIdentity = field(default_factory=PluginIdentity)
    architecture: ArchitectureContract = field(default_factory=ArchitectureContract)
    capabilities: CapabilityContract = field(default_factory=CapabilityContract)
    ownership: OwnershipContract = field(default_factory=OwnershipContract)
    authority: AuthorityContract = field(default_factory=AuthorityContract)
    lifecycle: LifecycleContract = field(default_factory=LifecycleContract)
    observability: EvidenceContract = field(default_factory=EvidenceContract)
    verification: VerificationContract = field(default_factory=VerificationContract)
    contribution: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.contribution, tuple):
            object.__setattr__(self, "contribution", tuple(self.contribution))


# ── Module-level accessors (ADR-0015 contracts purity) ──────────────


def is_plugin_contract_empty(contract: PluginContract) -> bool:
    """PluginContract 全部段都是默认值 = 未声明。"""
    return (
        contract.identity == PluginIdentity()
        and contract.architecture == ArchitectureContract()
        and contract.capabilities == CapabilityContract()
        and contract.ownership == OwnershipContract()
        and contract.authority == AuthorityContract()
        and contract.lifecycle == LifecycleContract()
        and contract.observability == EvidenceContract()
        and contract.verification == VerificationContract()
        and not contract.contribution
    )


def plugin_contract_control_slots(contract: PluginContract) -> tuple[ControlSlot, ...]:
    """从 ``architecture.control_slots`` 提取槽位列表。"""
    return contract.architecture.control_slots


def plugin_contract_functional_group(
    contract: PluginContract,
) -> FunctionalGroup | None:
    """从 ``architecture.group`` 提取群。"""
    return contract.architecture.group


# ── ADR-0110 PR-A：3-key 归一 seam ─────────────────────────────────


def logic_address_to_plugin_contract(address: LogicAddress) -> PluginContract:
    """Fold a flat 6-dim ``LogicAddress`` into the canonical 5-section contract.

    ADR-0110 D2 maps the legacy flat struct into PluginContract's sections:

    - functional_group → architecture.group
    - control_slot     → architecture.control_slots
    - scope            → lifecycle.allowed_scopes
    - authority        → authority.grants
    - evidence         → observability.descriptors
    - revision         → identity.version

    Missing dims remain missing (None / empty tuple); no defaults are forced.
    Use during the deprecation window to bridge the 195 call sites currently
    passing ``logic_address=LogicAddress(...)`` to ``@plugin(...)``.
    """
    return PluginContract(
        identity=PluginIdentity(version=address.revision or ""),
        architecture=ArchitectureContract(
            group=address.functional_group,
            control_slots=(address.control_slot,) if address.control_slot else (),
        ),
        lifecycle=LifecycleContract(
            allowed_scopes=(address.scope,) if address.scope else (),
        ),
        authority=AuthorityContract(grants=tuple(address.authority)),
        observability=EvidenceContract(descriptors=tuple(address.evidence)),
    )


def compose_plugin_contract(
    *,
    functional_group: FunctionalGroup | str | None = None,
    logic_address: LogicAddress | None = None,
    contract: PluginContract | None = None,
) -> PluginContract:
    """Unify the three ``@plugin(...)`` declaration keys into canonical form.

    Priority order is **contract > logic_address > functional_group**. The
    highest-priority non-None key wins; lower-priority keys are silently
    ignored (per ADR-0110 D3 — alias behaviour, callers choose the canonical
    form over time).

    - contract        → returned as-is (already canonical)
    - logic_address   → folded via ``logic_address_to_plugin_contract``
    - functional_group → wrapped into a minimal contract with only
      ``architecture.group`` populated
    - all None        → empty ``PluginContract()`` (author-declared nothing)

    Authoritative seam for ``@plugin(...)`` decoration normalization per
    ADR-0110 D1 + D3.
    """
    if contract is not None:
        return contract

    if logic_address is not None:
        return logic_address_to_plugin_contract(logic_address)

    if functional_group is not None:
        if isinstance(functional_group, str):
            group_value = parse_functional_group(functional_group)
        else:
            group_value = functional_group
        return PluginContract(architecture=ArchitectureContract(group=group_value))

    return PluginContract()


def contract_snapshot_for_meta(contract: PluginContract) -> dict[str, object]:
    """Project the canonical contract into a JSON-friendly dict for plugin meta.

    Stored on cordis plugin as ``meta["contract_snapshot"]`` so downstream
    readers always see the canonical 5-section form regardless of which
    legacy key (functional_group / logic_address) the author used.

    The snapshot is informational; runtime code should keep reading via
    ``lca.harness.plugin.plugin_manifest.PluginDefinition.contract`` (the
    typed PluginContract), not by parsing this dict.
    """
    return {
        "identity": {
            "id": contract.identity.id,
            "version": contract.identity.version,
            "owner": contract.identity.owner,
        },
        "architecture": {
            "group": (
                contract.architecture.group.value
                if contract.architecture.group is not None
                else None
            ),
            "role": contract.architecture.role,
            "control_slots": [slot.value for slot in contract.architecture.control_slots],
        },
        "capabilities": {
            "provides": list(contract.capabilities.provides),
            "requires": list(contract.capabilities.requires),
            "effect_classes": list(contract.capabilities.effect_classes),
        },
        "lifecycle": {
            "allowed_scopes": [s.value for s in contract.lifecycle.allowed_scopes],
            "lease_seconds": contract.lifecycle.lease_seconds,
            "dispose_strategy": contract.lifecycle.dispose_strategy,
        },
        "authority": {
            "grants": list(contract.authority.grants),
            "risk_level": contract.authority.risk_level,
            "requires_approval": contract.authority.requires_approval,
        },
        "observability": {
            "descriptors": list(contract.observability.descriptors),
            "privacy_class": contract.observability.privacy_class,
            "replay_safe": contract.observability.replay_safe,
        },
        "verification": {
            "schemas": list(contract.verification.schemas),
            "fixtures": list(contract.verification.fixtures),
            "property_tests": list(contract.verification.property_tests),
            "test_suite": contract.verification.test_suite,
        },
    }


__all__ = [
    "ArchitectureContract",
    "AuthorityContract",
    "CapabilityContract",
    "EvidenceContract",
    "LifecycleContract",
    "OwnershipContract",
    "PluginContract",
    "PluginIdentity",
    "VerificationContract",
    "compose_plugin_contract",
    "contract_snapshot_for_meta",
    "is_plugin_contract_empty",
    "logic_address_to_plugin_contract",
    "plugin_contract_control_slots",
    "plugin_contract_functional_group",
]
