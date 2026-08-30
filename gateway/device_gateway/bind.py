"""Application-scoped device-to-machine resolution."""

from __future__ import annotations

from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.models import Device
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.transport import DeviceTransport
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.protocols.infra import MachineResolver, MachineTransport
from lca.layer0_infra.plane.paths import outputs_under
from lca.layer0_infra.sandbox.host_settings import load_host_settings


def plane_ref_for_device(device: Device) -> PlaneRef:
    """The only writer of a machine PlaneRef. Root is the device workspace."""
    settings = load_host_settings()
    root = device.workspace.strip() or str(settings.workspace())
    outputs = outputs_under(root)
    return PlaneRef(
        id=device.device_id,
        label=device.hostname or device.device_id,
        kind=PlaneKind.MACHINE,
        root=root,
        outputs_dir=outputs,
        platform=device.platform,
        home=device.home,
    )


class DeviceMachineResolver(MachineResolver):
    """Resolve machines from the DeviceRegistry owned by one Gateway app."""

    def __init__(self, registry: DeviceRegistry, hub: DeviceHub) -> None:
        self._registry = registry
        self._hub = hub

    def resolve_machine(self, device_id: str | None = None) -> PlaneRef | None:
        device = self._registry.select_online(device_id)
        if device is None:
            return None
        return plane_ref_for_device(device)

    def resolve_transport(self, device_id: str) -> MachineTransport | None:
        return DeviceTransport.for_device(self._registry, self._hub, device_id)


__all__ = ["DeviceMachineResolver", "plane_ref_for_device"]
