"""兼容 shim —— 请改用 ``lca.layer0_infra.component_registry``（ADR-0016）。"""

from lca.layer0_infra.component_registry import (
    ComponentRegistry,
    NamedRegistry,
    RegistryKeyError,
    get_global_registry,
)

__all__ = [
    "ComponentRegistry",
    "NamedRegistry",
    "RegistryKeyError",
    "get_global_registry",
]
