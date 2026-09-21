"""Execution-environment catalog — read model for where the agent can run."""

from lca.infrastructure.environment.catalog import CompositeEnvironmentCatalog
from lca.infrastructure.environment.factory import build_environment_catalog
from lca.infrastructure.environment.providers import (
    DeviceEnvironmentProvider,
    SandboxEnvironmentProvider,
)

__all__ = [
    "CompositeEnvironmentCatalog",
    "DeviceEnvironmentProvider",
    "SandboxEnvironmentProvider",
    "build_environment_catalog",
]
