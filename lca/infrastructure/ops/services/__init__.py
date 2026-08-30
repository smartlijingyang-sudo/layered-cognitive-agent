"""Service implementations."""

from lca.infrastructure.ops.config import OpsConfig
from lca.infrastructure.ops.registry import ServiceRegistry
from lca.infrastructure.ops.services.daemon import DaemonService
from lca.infrastructure.ops.services.gateway import GatewayService
from lca.infrastructure.ops.services.infra import InfraService
from lca.infrastructure.ops.services.lobehub import LobeHubService
from lca.infrastructure.ops.services.onlyboxes import OnlyboxesService
from lca.infrastructure.ops.sudo import Sudo

__all__ = [
    "DaemonService",
    "GatewayService",
    "InfraService",
    "LobeHubService",
    "OnlyboxesService",
    "build_registry",
]


def build_registry(config: OpsConfig) -> ServiceRegistry:
    """Create a ServiceRegistry with all services from config."""
    registry = ServiceRegistry()
    registry.register(InfraService(config.infra, config.state_dir))
    registry.register(GatewayService(config.gateway, config.state_dir, config.root))
    registry.register(LobeHubService(config.lobehub, config.gateway, config.state_dir, config.root))

    sudo = Sudo(config.root / config.sudo_pass_file)
    registry.register(
        DaemonService(config.daemon, config.gateway, config.state_dir, config.root, sudo)
    )
    registry.register(OnlyboxesService(config.onlyboxes, config.root))
    return registry
