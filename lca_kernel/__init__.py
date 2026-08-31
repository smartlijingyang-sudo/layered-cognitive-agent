"""LCA Kernel —— 编译 profile 到运行中进程。

8 大职责见 ADR-0115 决定 1 + ADR-0111 修订版;本模块是唯一公共面。

Public API
----------
- :func:`compile_profile` —— path → ``CompiledRunPlan``(纯函数)。
- :func:`run_kernel` —— ``CompiledRunPlan`` → booted ``cordis.Context``(主入口)。
- :func:`stop_kernel` —— graceful shutdown。
- :func:`run_kernel_lifespan` —— AsyncContextManager 桥给 ASGI lifespan。
- :func:`install_compile_result` —— 把编译产物 provide 到 ctx(transport 用)。
- :class:`KernelError` / :exc:`FailLoudError` / :exc:`StageError`
- :class:`Stage` (IntEnum SSOT)
- :class:`EnvSnapshot` (immutable env provenance)
- :data:`FAIL_LOUD_RELEASE_TIMEOUT_MS` (deepseek 借鉴常量)

Why a dedicated module
----------------------
Kernel is the single seam where "声明文本" → "运行中进程" 的转换发生。
任何 transport(Starlette / JSON-RPC / stdio)只调
:func:`run_kernel_lifespan` 或 :func:`run_kernel`;它们不直接构造
cordis Context。Kernel 不知道有 transport 存在,通过 ``lint-imports`` 强制
(ADR-0115 决定 3)。
"""

from typing import TYPE_CHECKING

from lca_kernel.boot import (
    boot_entries,
    install_compile_result,
    run_kernel,
    run_resolved_kernel,
    stop_kernel,
)
from lca_kernel.errors import (
    FailLoudError,
    KernelError,
    ReloadError,
    ReloadReason,
    StageError,
)
from lca_kernel.hmr import (
    DEFAULT_PATCH_PATH,
    MIN_DEBOUNCE_MS,
    PATCH_EVENT_KIND,
    PatchConfig,
    PatchEvent,
    PatchWatcher,
    PollingPatchWatcher,
    summarize_patch,
    validate_patch,
)
from lca_kernel.lifecycle import (
    FAIL_LOUD_RELEASE_TIMEOUT_MS,
    DefaultShutdownCoordinator,
    ShutdownCoordinator,
    create_shutdown_coordinator,
    install_fail_loud,
    install_signal_handlers,
    run_kernel_lifespan,
)
from lca_kernel.stages import Stage

if TYPE_CHECKING:
    from lca.harness.profile.resolve import ResolvedProfile


def compile_profile(resolved: "ResolvedProfile") -> object:
    """编译 ``ResolvedProfile`` → ``CompiledRunPlan``(公共 alias)。

    命名遵循 ADR-0106 §8.1 函数前缀表(``compile_*``);实现委托给
    :mod:`lca_kernel.plan`。
    """
    from lca_kernel.plan import compile_run_plan

    return compile_run_plan(resolved)


__all__ = [
    "DEFAULT_PATCH_PATH",
    "FAIL_LOUD_RELEASE_TIMEOUT_MS",
    "MIN_DEBOUNCE_MS",
    "PATCH_EVENT_KIND",
    "DefaultShutdownCoordinator",
    "FailLoudError",
    "KernelError",
    "PatchConfig",
    "PatchEvent",
    "PatchWatcher",
    "PollingPatchWatcher",
    "ReloadError",
    "ReloadReason",
    "ShutdownCoordinator",
    "Stage",
    "StageError",
    "boot_entries",
    "compile_profile",
    "create_shutdown_coordinator",
    "install_compile_result",
    "install_fail_loud",
    "install_signal_handlers",
    "run_kernel",
    "run_kernel_lifespan",
    "run_resolved_kernel",
    "stop_kernel",
    "summarize_patch",
    "validate_patch",
]
