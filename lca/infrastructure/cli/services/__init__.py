"""Service implementations.

ADR-0119 决定 4:lca-ops 不再管 LCA 进程的 start/stop/restart (SIGTERM 由 K6
``lca_kernel.lifecycle`` 守护)。但 heal 仍然要能自愈 —— ``KernelServeService``
只暴露 ``state()`` / ``heal()``,负责探测 ``/health`` 与 spawn 后台进程。
start / stop / restart 显式 raise NotImplementedError,与 ADR 一致。

本模块还管 lobehub / infra / daemon / onlyboxes 等外部平台服务。
"""

from lca.infrastructure.cli.config import OpsConfig
from lca.infrastructure.cli.registry import ServiceRegistry
from lca.infrastructure.cli.services.daemon import DaemonService
from lca.infrastructure.cli.services.infra import InfraService
from lca.infrastructure.cli.services.kernel_serve import KernelServeService
from lca.infrastructure.cli.services.lobehub import LobeHubService
from lca.infrastructure.cli.services.onlyboxes import OnlyboxesService
from lca.infrastructure.cli.sudo import Sudo

__all__ = [
    "DaemonService",
    "InfraService",
    "KernelServeService",
    "LobeHubService",
    "OnlyboxesService",
    "build_registry",
]


def build_registry(config: OpsConfig) -> ServiceRegistry:
    """Create a ServiceRegistry with all services from config.

    ADR-0119 决定 4 + PR-3:KernelServeService 提供 state/heal(只读 + 自愈),
    start/stop/restart 由 NotImplementedError 拒绝。LobeHub / Infra / Daemon /
    Onlyboxes 仍由 ``lca-ops`` 子命令管理。
    """
    registry = ServiceRegistry()
    registry.register(KernelServeService(config.kernel_serve, config.root))
    registry.register(InfraService(config.infra, config.state_dir))
    registry.register(
        LobeHubService(config.lobehub, config.kernel_serve, config.state_dir, config.root)
    )

    sudo = Sudo(config.root / config.sudo_pass_file)
    registry.register(
        DaemonService(config.daemon, config.kernel_serve, config.state_dir, config.root, sudo)
    )
    registry.register(OnlyboxesService(config.onlyboxes, config.root))
    return registry
