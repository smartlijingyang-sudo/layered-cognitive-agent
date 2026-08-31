"""Service implementations.

ADR-0119 决定 4:lca-ops 不再管 LCA 进程 — LCA 进程由 ``python -m lca_kernel serve``
自己管 SIGTERM/SIGINT(K6 守护)。本模块只管 lobehub / infra / daemon / onlyboxes
等外部平台服务。
"""

from lca.infrastructure.cli.config import OpsConfig
from lca.infrastructure.cli.registry import ServiceRegistry
from lca.infrastructure.cli.services.daemon import DaemonService
from lca.infrastructure.cli.services.infra import InfraService
from lca.infrastructure.cli.services.lobehub import LobeHubService
from lca.infrastructure.cli.services.onlyboxes import OnlyboxesService
from lca.infrastructure.cli.sudo import Sudo

__all__ = [
    "DaemonService",
    "InfraService",
    "LobeHubService",
    "OnlyboxesService",
    "build_registry",
]


def build_registry(config: OpsConfig) -> ServiceRegistry:
    """Create a ServiceRegistry with all services from config.

    ADR-0119 决定 4:网关 (LCA 进程) 不再由本 registry 管理。LobeHub / Infra /
    Daemon / Onlyboxes 由 ``lca-ops`` 子命令管理,LCA 进程由
    ``python -m lca_kernel serve`` 直管。
    """
    registry = ServiceRegistry()
    registry.register(InfraService(config.infra, config.state_dir))
    # ADR-0119 决定 4:GatewayService 已删除(LCA 进程由 python -m lca_kernel serve 自管)
    # daemon 仍需要 GatewayConfig 知道 host/port/base_url/health_url,
    # GatewayConfig 在 lca.infrastructure.cli.config 保留(删 entry/watch 字段)
    registry.register(LobeHubService(config.lobehub, config.gateway, config.state_dir, config.root))

    sudo = Sudo(config.root / config.sudo_pass_file)
    registry.register(
        DaemonService(config.daemon, config.gateway, config.state_dir, config.root, sudo)
    )
    registry.register(OnlyboxesService(config.onlyboxes, config.root))
    return registry
