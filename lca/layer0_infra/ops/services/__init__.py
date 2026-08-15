"""Service implementations."""

from lca.layer0_infra.ops.services.daemon import DaemonService
from lca.layer0_infra.ops.services.gateway import GatewayService
from lca.layer0_infra.ops.services.infra import InfraService
from lca.layer0_infra.ops.services.lobehub import LobeHubService

__all__ = [
    "DaemonService",
    "GatewayService",
    "InfraService",
    "LobeHubService",
    "build_registry",
]


def build_registry(config):
    """Create a ServiceRegistry with all services from config."""
    from lca.layer0_infra.ops.registry import ServiceRegistry

    registry = ServiceRegistry()
    registry.register(InfraService(config.infra, config.state_dir))
    registry.register(GatewayService(config.gateway, config.state_dir, config.root))
    registry.register(LobeHubService(config.lobehub, config.gateway, config.state_dir, config.root))
    from lca.layer0_infra.ops.sudo import Sudo

    sudo = Sudo(config.root / config.sudo_pass_file)
    registry.register(
        DaemonService(config.daemon, config.gateway, config.state_dir, config.root, sudo)
    )
    return registry
