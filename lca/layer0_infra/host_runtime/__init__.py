"""Host runtime package — YAML-driven host environment management.

Usage::

    from lca.layer0_infra.host_runtime.config import HostRuntimeConfig
    from lca.layer0_infra.host_runtime.environment import HostEnvironment

    config = HostRuntimeConfig.from_yaml("lca-host.yaml")
    env = HostEnvironment(config)
    env.provision("sandbox-user")
"""
