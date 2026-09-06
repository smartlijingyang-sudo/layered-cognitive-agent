"""Profile boot product data seam (ADR-0195 P4-K03).

``ProfileBootProducts`` is the only boot-time attachment for resolved profile
and compiled plan facts. Compile logic lives in
:mod:`lca.harness.composition.boot_compile`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.contracts.mechanisms.capability import MissingCapabilityError

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.protocols.state.plan import CompiledRunPlan
    from lca.harness.profile.resolve import ResolvedProfile


_BOOT_PRODUCTS_CONTEXT_KEY = "_lca_profile_boot_products"


@dataclass(frozen=True, slots=True)
class ProfileBootProducts:
    """Immutable declaration + optional compiled plan from one boot."""

    resolved_profile: ResolvedProfile | None = None
    compiled_run_plan: CompiledRunPlan | None = None


def attach_profile_boot_products(
    scope: Context,
    products: ProfileBootProducts,
) -> ProfileBootProducts:
    """Attach boot products atomically; reject re-interpretation."""
    existing = profile_boot_products_from_scope(scope)
    if existing is not None:
        if existing != products:
            raise RuntimeError("Profile boot products are already attached to this scope")
        return existing
    scope.__dict__[_BOOT_PRODUCTS_CONTEXT_KEY] = products
    return products


def profile_boot_products_from_scope(scope: Context) -> ProfileBootProducts | None:
    products = scope.__dict__.get(_BOOT_PRODUCTS_CONTEXT_KEY)
    if products is None:
        return None
    if not isinstance(products, ProfileBootProducts):
        raise RuntimeError("Profile boot products on scope have an invalid type")
    return products


def resolved_profile_from_scope(scope: Context) -> ResolvedProfile | None:
    products = profile_boot_products_from_scope(scope)
    return None if products is None else products.resolved_profile


def compiled_plan_from_scope(scope: Context) -> CompiledRunPlan:
    products = profile_boot_products_from_scope(scope)
    if products is None or products.compiled_run_plan is None:
        raise MissingCapabilityError("compiled_run_plan")
    return products.compiled_run_plan


def compile_profile_boot_products(resolved: ResolvedProfile) -> ProfileBootProducts:
    from lca.harness.composition.boot_compile import (
        compile_profile_boot_products as _compile,
    )

    return _compile(resolved)


__all__ = [
    "ProfileBootProducts",
    "attach_profile_boot_products",
    "compile_profile_boot_products",
    "compiled_plan_from_scope",
    "profile_boot_products_from_scope",
    "resolved_profile_from_scope",
]


def __getattr__(name: str) -> object:
    if name == "compile_profile_boot_products":
        from lca.harness.composition.boot_compile import compile_profile_boot_products

        return compile_profile_boot_products
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
