"""Host runtime package — YAML-driven host environment management.

Usage::

    from lca.infrastructure.host_runtime.config import HostRuntimeConfig
    from lca.infrastructure.host_runtime.environment import HostEnvironment

    config = HostRuntimeConfig.from_yaml("lca-host.yaml")
    env = HostEnvironment(config)
    env.provision("sandbox-user")
"""
