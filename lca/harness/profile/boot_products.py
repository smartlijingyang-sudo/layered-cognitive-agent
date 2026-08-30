"""Profile 启动产物的唯一读取接缝。

Profile 启动会产生两项不可变产物：解析后的插件声明，以及由该声明编译的
运行计划。它们必须作为同一份 boot-time 事实被后续的组合、诊断和运行路径
读取；调用方不应各自从 ``Context`` 的任意属性或原始 ``__dict__`` 推断其
存在、名称或关联关系。检查视图由 ``resolved_profile`` 派生，不得再写入
平行的 ``Context.entries``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.contracts.mechanisms.capability import MissingCapabilityError

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.harness.profile.resolve import ResolvedProfile


_BOOT_PRODUCTS_CONTEXT_KEY = "_lca_profile_boot_products"


@dataclass(frozen=True, slots=True)
class ProfileBootProducts:
    """同一次 Profile 启动产生的不可变声明与运行计划。

    ``resolved_profile`` 与 ``compiled_run_plan`` 必须由同一个启动过程派生。
    程序化入口可只附加解析 Profile，运行时闭合仍由夹具按能力读取路径验证；
    计划绑定夹具可只附加计划；生产启动则始终附加完整产物对。
    """

    resolved_profile: ResolvedProfile | None = None
    compiled_run_plan: CompiledRunPlan | None = None


def compile_profile_boot_products(resolved: ResolvedProfile) -> ProfileBootProducts:
    """从已解析声明编译生产或显式测试范围的完整启动产物。"""

    from lca.harness.profile.plan_compiler import CompileOptions, compile_plan
    from lca.harness.profile.runtime_binding_validator import profile_allows_test_defaults

    return ProfileBootProducts(
        resolved_profile=resolved,
        compiled_run_plan=compile_plan(
            resolved,
            options=CompileOptions(
                require_executable_phase_graph=not profile_allows_test_defaults(resolved)
            ),
        ),
    )


def attach_profile_boot_products(
    scope: Context,
    products: ProfileBootProducts,
) -> ProfileBootProducts:
    """将一份启动产物原子地附加到 scope，拒绝后续重解释。"""

    existing = profile_boot_products_from_scope(scope)
    if existing is not None:
        if existing != products:
            raise RuntimeError("Profile boot products are already attached to this scope")
        return existing
    scope.__dict__[_BOOT_PRODUCTS_CONTEXT_KEY] = products
    return products


def profile_boot_products_from_scope(scope: Context) -> ProfileBootProducts | None:
    """返回由 Profile 启动附加的产物；缺失时返回 ``None``。"""

    products = scope.__dict__.get(_BOOT_PRODUCTS_CONTEXT_KEY)
    if products is None:
        return None
    if not isinstance(products, ProfileBootProducts):
        raise RuntimeError("Profile boot products on scope have an invalid type")
    return products


def resolved_profile_from_scope(scope: Context) -> ResolvedProfile | None:
    """读取启动时解析的 Profile，而不泄漏 Context 属性名称。"""

    products = profile_boot_products_from_scope(scope)
    return None if products is None else products.resolved_profile


def compiled_plan_from_scope(scope: Context) -> CompiledRunPlan:
    """读取启动时冻结的运行计划，缺失时以稳定错误失败关闭。"""

    products = profile_boot_products_from_scope(scope)
    if products is None or products.compiled_run_plan is None:
        raise MissingCapabilityError("compiled_run_plan")
    return products.compiled_run_plan


__all__ = [
    "ProfileBootProducts",
    "attach_profile_boot_products",
    "compile_profile_boot_products",
    "compiled_plan_from_scope",
    "profile_boot_products_from_scope",
    "resolved_profile_from_scope",
]
