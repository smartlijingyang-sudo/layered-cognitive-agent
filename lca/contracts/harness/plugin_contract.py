"""PluginContract 9 段契约（ADR-0069 §六 + tracker §12）。

PluginContract 是 plugin 作者的可选 typed section：**不替换**
PluginDefinition，作为可选并存（tracker §12.1 user 拍板）。plugin
作者渐进迁移：核心插件（``repeat_tool_call`` / ``stop_rule`` /
``decision_gate`` / 感知）填字段作为示范，其余插件按需渐进。

9 段：

1. ``identity`` — PluginIdentity（id / version / owner）
2. ``architecture`` — ArchitectureContract（group / role / control slots）
3. ``capabilities`` — CapabilityContract（provides / requires / effect classes）
4. ``ownership`` — OwnershipContract（reads / emits / state authority）
5. ``authority`` — AuthorityContract（grant / risk / approval requirements）
6. ``lifecycle`` — LifecycleContract（allowed scopes / lease / dispose）
7. ``observability`` — EvidenceContract（descriptors / privacy / replay）
8. ``verification`` — VerificationContract（schemas / fixtures / property tests）
9. ``contribution`` — 与 ``architecture.control_slots`` 等价的 legacy 段（PR-2
   引入；保持 PluginContract 与 PluginDefinition.control 字段双向兼容）

注意：``PluginContract`` 是 **协议**（不是强制门禁）。PluginManifest
可填可空；空 ``PluginContract()`` 等价于"作者未声明"。

ADR-0015 contracts 纯类型契约：所有派生值通过 module-level 函数访问。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot, validate_slot_iterable
from lca.contracts.atoms.functional_group import FunctionalGroup, parse_functional_group
from lca.contracts.atoms.scope import Scope, parse_scope

# ── Section dataclasses (all Optional / default-empty) ──────────────


@dataclass(frozen=True, slots=True)
class PluginIdentity:
    """plugin 身份元数据。"""

    id: str = ""
    version: str = ""
    owner: str = ""  # team / person / role


@dataclass(frozen=True, slots=True)
class ArchitectureContract:
    """架构归属：群 / role / control slots。"""

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

    全部字段 optional；缺失段不阻断 plugin 加载。``contribution`` 段
    与 ``PluginDefinition.control`` 字段是同一信息的两种表达：plugin
    作者二选一即可；resolver 阶段合并两者去重。

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
    "is_plugin_contract_empty",
    "plugin_contract_control_slots",
    "plugin_contract_functional_group",
]
