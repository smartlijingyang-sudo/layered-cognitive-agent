"""Profile 编译层的生产运行闭合目录。

运行闭合描述的是一个 Profile 要如何装配为可运行的生产 Agent：哪些
capability 必须具备 provider、缺失时允许哪种 fixture 回退、以及诊断应指向
哪个装配模块。它不是跨层数据契约，也不属于 ``lca.contracts``；contracts
只承载编译完成的不可变 ``ProviderBinding`` 事实。

本模块是 Profile 输入规范化、闭合验证、CapabilityPlan 投影及其诊断的唯一
策略 seam。由目录派生的只读表仅为诊断和测试提供稳定读取面，不应在其他模块
重新维护平行映射。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class FallbackPolicy(str, Enum):
    """Profile 缺少 runtime capability 时允许的显式装配策略。"""

    PRODUCTION = "production"
    TEST_DEFAULT = "test_default"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class RuntimeClosureRequirement:
    """一个生产 runtime closure seam 的完整装配要求。"""

    capability: str
    provider_hint: str
    default_fallback_policy: FallbackPolicy = FallbackPolicy.PRODUCTION

    def __post_init__(self) -> None:
        if not isinstance(self.capability, str) or not self.capability:
            raise ValueError("RuntimeClosureRequirement.capability must be a non-empty string")
        if not isinstance(self.provider_hint, str) or not self.provider_hint:
            raise ValueError("RuntimeClosureRequirement.provider_hint must be a non-empty string")
        if not isinstance(self.default_fallback_policy, FallbackPolicy):
            raise TypeError("default_fallback_policy must be a FallbackPolicy")


_RUNTIME_CLOSURE_CATALOG: tuple[RuntimeClosureRequirement, ...] = (
    RuntimeClosureRequirement(
        "idempotency_store",
        "lca.plugins.seam_definitions.idempotency_store",
    ),
    RuntimeClosureRequirement(
        "effect_handler_registry",
        "lca.plugins.seam_definitions.effect_handler",
    ),
    RuntimeClosureRequirement(
        "effect_gateway_factory",
        "lca.plugins.providers.declarative_runtime_seams",
    ),
    RuntimeClosureRequirement(
        "checkpoint_state_resolver_factory",
        "lca.plugins.providers.declarative_runtime_seams",
    ),
    RuntimeClosureRequirement(
        "result_finalizer_factory",
        "lca.plugins.providers.declarative_runtime_seams",
    ),
    RuntimeClosureRequirement(
        "delta_handler_registry",
        "lca.plugins.seam_definitions.delta_handler",
    ),
    RuntimeClosureRequirement(
        "delta_reducer_factory",
        "lca.plugins.providers.declarative_runtime_seams",
    ),
    RuntimeClosureRequirement(
        "declarative_interpreter_factory",
        "lca.plugins.providers.declarative_runtime_seams",
    ),
    RuntimeClosureRequirement(
        "runtime_journal_factory",
        "lca.plugins.providers.declarative_runtime_seams",
    ),
    RuntimeClosureRequirement(
        "loop_guard_evaluator",
        "lca.plugins.providers.loop_guard",
    ),
    RuntimeClosureRequirement(
        "evidence_store",
        "lca.plugins.seam_definitions.observability.evidence_store",
    ),
    RuntimeClosureRequirement(
        "stop_policy",
        "lca.plugins.state.stop_policy",
    ),
    RuntimeClosureRequirement(
        "reducer",
        "lca.runtime.reducer",
    ),
    RuntimeClosureRequirement(
        "artifact_closure",
        "lca.plugins.providers.artifact_closure",
    ),
    RuntimeClosureRequirement(
        "phase_observer",
        "lca.plugins.providers.phase_observer",
    ),
    RuntimeClosureRequirement(
        "resume_input_adapters",
        "lca.plugins.registries.factory_seams",
    ),
)
_RUNTIME_CLOSURE_BY_CAPABILITY: Mapping[str, RuntimeClosureRequirement] = MappingProxyType(
    {requirement.capability: requirement for requirement in _RUNTIME_CLOSURE_CATALOG}
)

# 诊断与测试的稳定只读投影；它们由 catalog 派生，禁止单独维护。
RUNTIME_CLOSURE_REQUIREMENTS: Mapping[str, str] = MappingProxyType(
    {requirement.capability: requirement.provider_hint for requirement in _RUNTIME_CLOSURE_CATALOG}
)
RUNTIME_CLOSURE_FALLBACK_POLICIES: Mapping[str, FallbackPolicy] = MappingProxyType(
    {
        requirement.capability: requirement.default_fallback_policy
        for requirement in _RUNTIME_CLOSURE_CATALOG
    }
)


def runtime_closure_requirements() -> tuple[RuntimeClosureRequirement, ...]:
    """返回按目录顺序稳定的生产闭合 requirement。"""
    return _RUNTIME_CLOSURE_CATALOG


def runtime_closure_requirement(capability: str) -> RuntimeClosureRequirement | None:
    """按 capability 查询 requirement；非闭合 capability 返回 ``None``。"""
    return _RUNTIME_CLOSURE_BY_CAPABILITY.get(capability)


def default_fallback_policy(
    capability: str,
    *,
    default: FallbackPolicy = FallbackPolicy.PRODUCTION,
) -> FallbackPolicy:
    """返回 closure capability 的目录默认策略，其他 capability 使用调用方默认值。"""
    requirement = runtime_closure_requirement(capability)
    return requirement.default_fallback_policy if requirement is not None else default


def closure_requirements() -> tuple[str, ...]:
    """返回按目录顺序稳定的 closure capability key。"""
    return tuple(requirement.capability for requirement in _RUNTIME_CLOSURE_CATALOG)


def closure_provider_hint(capability: str) -> str | None:
    """返回 closure capability 的期望 provider 模块路径。"""
    requirement = runtime_closure_requirement(capability)
    return requirement.provider_hint if requirement is not None else None


__all__ = [
    "RUNTIME_CLOSURE_FALLBACK_POLICIES",
    "RUNTIME_CLOSURE_REQUIREMENTS",
    "FallbackPolicy",
    "RuntimeClosureRequirement",
    "closure_provider_hint",
    "closure_requirements",
    "default_fallback_policy",
    "runtime_closure_requirement",
    "runtime_closure_requirements",
]
