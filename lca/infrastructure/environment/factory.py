"""Factory wiring for the execution-environment catalog."""

from __future__ import annotations

from lca.contracts.models.core.environment.model import environment_from_plane
from lca.contracts.models.core.state.plane import PlaneBindings, PlaneKind
from lca.contracts.protocols import Sandbox
from lca.contracts.protocols.runtime.environment import (
    DeviceProvider,
    EnvironmentCatalog,
    EnvironmentProvider,
)
from lca.contracts.protocols.runtime.infra.infra import MachineResolver
from lca.infrastructure.environment.catalog import CompositeEnvironmentCatalog
from lca.infrastructure.environment.providers import (
    DeviceEnvironmentProvider,
    SandboxEnvironmentProvider,
)
from lca.infrastructure.runtime_plane.resolve.resolve import ref_of, sandbox_ref_from


def build_environment_catalog(
    bindings: PlaneBindings | None,
    sandbox: Sandbox | None = None,
    machine_resolver: MachineResolver | None = None,
) -> EnvironmentCatalog:
    """Assemble the catalog from the current run's plane context.

    Providers are only added when their source is actually present, so a
    sandbox-only run sees the sandbox and no machines, and vice versa.
    """
    bound = bindings if bindings is not None else PlaneBindings(primary=None)

    providers: list[EnvironmentProvider] = []
    sandbox_ref = ref_of(bound, PlaneKind.SANDBOX)
    if sandbox_ref is None and sandbox is not None:
        sandbox_ref = sandbox_ref_from(sandbox)
    if sandbox_ref is not None:
        providers.append(SandboxEnvironmentProvider(sandbox_ref))
    if isinstance(machine_resolver, DeviceProvider):
        providers.append(DeviceEnvironmentProvider(machine_resolver))

    current = None
    if bound.primary is not None:
        current = environment_from_plane(bound.primary, is_current=True)
    return CompositeEnvironmentCatalog(providers, current=current)


__all__ = ["build_environment_catalog"]
