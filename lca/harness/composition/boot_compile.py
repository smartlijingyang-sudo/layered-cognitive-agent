"""Boot-time profile compile helpers (ADR-0195 P4-K03)."""

from __future__ import annotations

from lca.harness.composition.plan_compiler import CompileOptions, compile_plan
from lca.harness.profile.boot.products import ProfileBootProducts
from lca.harness.profile.resolve.resolve import ResolvedProfile
from lca.harness.profile.validate.runtime_binding_validator import profile_allows_test_defaults


def compile_profile_boot_products(resolved: ResolvedProfile) -> ProfileBootProducts:
    """Compile the immutable boot product pair from a resolved profile."""
    from lca.harness.composition.observability_compile import compile_observability_boot_plan

    return ProfileBootProducts(
        resolved_profile=resolved,
        compiled_run_plan=compile_plan(
            resolved,
            options=CompileOptions(
                require_executable_phase_graph=not profile_allows_test_defaults(resolved)
            ),
        ),
        compiled_observability_plan=compile_observability_boot_plan(),
    )


__all__ = ["compile_profile_boot_products"]
