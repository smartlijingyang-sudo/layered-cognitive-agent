"""运行时闭包校验(K4)。

合并自 :mod:`lca.harness.profile.runtime_binding_validator` 与
:mod:`lca.harness.profile.runtime_closure`,ADR-0115 决定 1 K4。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.harness.profile.runtime_binding_validator import (
    MissingBindingError,
    RuntimeBindingValidator,
    profile_allows_test_defaults,
    validate_runtime_closure,
)
from lca.harness.profile.runtime_closure import (
    RUNTIME_CLOSURE_FALLBACK_POLICIES,
    RUNTIME_CLOSURE_REQUIREMENTS,
    FallbackPolicy,
    RuntimeClosureRequirement,
    closure_provider_hint,
    closure_requirements,
    default_fallback_policy,
    runtime_closure_requirement,
    runtime_closure_requirements,
)

if TYPE_CHECKING:
    from lca.harness.profile.projection import ResolvedProfileProjection
    from lca.harness.profile.resolve import ResolvedProfile


def assert_runtime_closure(
    resolved: ResolvedProfile,
    *,
    projection: ResolvedProfileProjection | None = None,
) -> None:
    """公共入口:验证 ``ResolvedProfile`` 是否提供完整的 runtime closure。"""
    validate_runtime_closure(resolved, projection=projection)
    return None


__all__ = [
    "RUNTIME_CLOSURE_FALLBACK_POLICIES",
    "RUNTIME_CLOSURE_REQUIREMENTS",
    "FallbackPolicy",
    "MissingBindingError",
    "RuntimeBindingValidator",
    "RuntimeClosureRequirement",
    "assert_runtime_closure",
    "closure_provider_hint",
    "closure_requirements",
    "default_fallback_policy",
    "profile_allows_test_defaults",
    "runtime_closure_requirement",
    "runtime_closure_requirements",
]
