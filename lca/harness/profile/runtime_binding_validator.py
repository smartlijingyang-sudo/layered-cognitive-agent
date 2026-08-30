"""Runtime binding 完整性验证（W1 / ADR-0076）。

Compile 阶段必须验证 runtime closure 的完整性：生产 profile 缺少关键
binding 时立即失败，不允许静默降级到默认实现。

W1 目标：
- 定义哪些 capability 是 runtime closure 必需的
- 在 compile 阶段验证这些 capability 都有 binding
- 缺失时抛 ``MissingBindingError``，包含缺失 capability、期望来源与候选 bundle / plugin
- 测试 profile 可通过 profile-level ``fallback_policy`` 显式放行（接受 test_default）
- provenance 可定位到具体 bundle / patch 来源

契约入口：
- :data:`RUNTIME_CLOSURE_REQUIREMENTS`（生产必需 capability 集合，单一事实源）
- :func:`validate_runtime_closure`（compile_plan 钩入）
- :exc:`MissingBindingError`（错误信息含 candidates / expected_from / fallback option）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.harness.profile.projection import ResolvedProfileProjection
from lca.harness.profile.runtime_closure import (
    FallbackPolicy,
    runtime_closure_requirements,
)

if TYPE_CHECKING:
    from lca.harness.profile.resolve import ResolvedProfile


class MissingBindingError(ValueError):
    """生产 profile 缺少关键 runtime binding（W1 / ADR-0076）。

    错误信息包含三类提示，便于修复：

    - ``capability`` — 主缺失的 capability key（若多个缺失则取首个）
    - ``expected_source`` — 期望的语义来源（如 ``bundle or profile patch``）
    - ``fallback_policy`` — 该 capability 的策略（生产严格 / 测试放行）
    - ``provider_hint`` — 提示哪个模块预期提供此 binding
    - ``candidates`` — 当前 profile 中可能提供此 binding 的 plugin / bundle（provenance）
    - ``additional`` — 同次校验中一并发现的其他缺失 binding（便于一次修完）
    """

    def __init__(
        self,
        capability: str,
        expected_source: str = "bundle or profile patch",
        *,
        fallback_policy: FallbackPolicy = FallbackPolicy.PRODUCTION,
        provider_hint: str | None = None,
        candidates: tuple[str, ...] = (),
        additional: tuple[tuple[str, FallbackPolicy, str | None], ...] = (),
    ) -> None:
        self.capability = capability
        self.expected_source = expected_source
        self.fallback_policy = fallback_policy
        self.provider_hint = provider_hint
        self.candidates = candidates
        self.additional = additional
        # 构造用户可读信息
        hint = f" Expected module: {provider_hint}." if provider_hint else ""
        cand_section = (
            "\nCandidates in profile (bundle / plugin / patch):\n  - " + "\n  - ".join(candidates)
            if candidates
            else "\nCandidates in profile: (none — capability is not provided by any enabled plugin)."
        )
        fallback_note = (
            ""
            if fallback_policy is FallbackPolicy.PRODUCTION
            else " (declared fallback_policy="
            f"{fallback_policy.value}; production should override or remove declaration)"
        )
        remediation = (
            "\nRemediation:\n"
            f"  - Enable a plugin that provides {capability!r} (see provider hint).{hint}\n"
            f"  - Or declare in profile top-level:\n"
            f"        fallback_policy:\n"
            f"          {capability}: {FallbackPolicy.TEST_DEFAULT.value}\n"
            "    (only allowed for test / null profiles)"
        )
        extras_section = ""
        if additional:
            extras_section = "\n\nAdditional missing bindings detected in same profile:"
            for cap, pol, ext_hint in additional:
                extras_section += (
                    f"\n  - {cap!r} (fallback_policy={pol.value}"
                    + (f", expected module={ext_hint}" if ext_hint else "")
                    + ")"
                )
        message = (
            f"Production profile missing required binding: {capability!r}.\n"
            f"Expected source: {expected_source}{fallback_note}."
            f"{cand_section}{remediation}{extras_section}"
        )
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RuntimeBindingValidator:
    """验证 ResolvedProfile 是否提供完整的 runtime closure binding。

    W1 / ADR-0076：生产 profile 必须显式提供所有 runtime closure 必需的
    capability binding，缺失时立即失败。

    Args:
        include_disabled: 是否将 ``disabled: true`` 的 plugin 视为有效 provider。
    """

    include_disabled: bool = False

    def allows_test_defaults(
        self,
        resolved: ResolvedProfile,
        *,
        projection: ResolvedProfileProjection | None = None,
    ) -> bool:
        """Return whether a runtime-closure capability explicitly permits test defaults.

        ``fallback_policy`` is a runtime-closure concern.  Keeping this decision
        here prevents boot and other callers from interpreting raw profile
        configuration differently.  Only policies attached to required runtime
        capabilities participate; an unrelated profile key cannot relax the
        executable phase-graph gate.
        """
        profile = ResolvedProfileProjection.reuse_or_build(
            resolved,
            include_disabled=self.include_disabled,
            projection=projection,
        )
        return any(
            _fallback_policy_for(
                profile,
                capability=requirement.capability,
                default=requirement.default_fallback_policy,
            )
            is FallbackPolicy.TEST_DEFAULT
            for requirement in runtime_closure_requirements()
        )

    def validate(
        self,
        resolved: ResolvedProfile,
        *,
        projection: ResolvedProfileProjection | None = None,
    ) -> None:
        """验证 runtime closure 完整性（缺失时抛 :exc:`MissingBindingError`）。

        校验流程：

        1. 收集所有 enabled plugin 的 ``provides``（含 contributor / replica）
        2. 遍历 :data:`RUNTIME_CLOSURE_REQUIREMENTS`，每条 capability 必有 provider
        3. 对每条缺失 binding，参考 ``resolved.fallback_policy`` 决定是否放行：

           - profile 显式声明 ``fallback_policy[<cap>]: test_default`` / ``off``
             → 放行（仅允许 test / null profile）
           - 否则默认 = ``production`` → 硬失败
        4. 失败时附带 ``provider_hint``、当前 profile 的 provenance 候选
           （bundle / patch / plugin）以及 remediation 提示
        """
        profile = ResolvedProfileProjection.reuse_or_build(
            resolved,
            include_disabled=self.include_disabled,
            projection=projection,
        )
        missing = _missing_bindings(profile)

        # 全部缺失一起抛：一次给出全部需要修的 binding，方便批量修复
        if missing:
            first_cap, first_pol, first_hint, first_cands = missing[0]
            additional = tuple((cap, pol, hint) for cap, pol, hint, _ in missing[1:])
            raise MissingBindingError(
                capability=first_cap,
                expected_source="bundle or profile patch",
                fallback_policy=first_pol,
                provider_hint=first_hint,
                candidates=first_cands,
                additional=additional,
            )


def _missing_bindings(
    profile: ResolvedProfileProjection,
) -> list[tuple[str, FallbackPolicy, str, tuple[str, ...]]]:
    """Return required capabilities that cannot use an explicit fallback."""
    missing: list[tuple[str, FallbackPolicy, str, tuple[str, ...]]] = []
    for requirement in runtime_closure_requirements():
        capability = requirement.capability
        if capability in profile.providers:
            continue
        declared = _fallback_policy_for(
            profile,
            capability=capability,
            default=requirement.default_fallback_policy,
        )
        if declared in (FallbackPolicy.TEST_DEFAULT, FallbackPolicy.OFF):
            continue
        missing.append(
            (
                capability,
                declared,
                requirement.provider_hint,
                profile.candidates_for(capability),
            )
        )
    return missing


def _fallback_policy_for(
    profile: ResolvedProfileProjection,
    *,
    capability: str,
    default: FallbackPolicy,
) -> FallbackPolicy:
    """Read one normalized runtime-closure fallback policy from the profile seam."""
    return FallbackPolicy(profile.fallback_for(capability, default=default.value))


def profile_allows_test_defaults(
    resolved: ResolvedProfile,
    *,
    projection: ResolvedProfileProjection | None = None,
) -> bool:
    """Return whether a Profile may use explicit runtime test defaults.

    This is the public policy seam for callers that need to distinguish a
    fixture Profile from a production runnable Profile.  It deliberately does
    not expose the raw ``fallback_policy`` mapping.
    """
    return RuntimeBindingValidator().allows_test_defaults(resolved, projection=projection)


def validate_runtime_closure(
    resolved: ResolvedProfile,
    *,
    projection: ResolvedProfileProjection | None = None,
) -> None:
    """便捷函数：验证 runtime closure 完整性。

    通过标准化的 Profile 投影读取 ``fallback_policy``：profile 声明
    ``test_default`` / ``off`` 时放行；缺省 / ``production`` 时硬失败。

    Raises:
        MissingBindingError: 缺少必需 binding（含完整 provenance 提示）
    """
    validator = RuntimeBindingValidator()
    validator.validate(resolved, projection=projection)


__all__ = [
    "MissingBindingError",
    "RuntimeBindingValidator",
    "profile_allows_test_defaults",
    "validate_runtime_closure",
]
