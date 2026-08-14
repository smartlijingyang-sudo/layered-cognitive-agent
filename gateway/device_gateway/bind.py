"""DeviceRegistry → machine PlaneRef + transport."""

from __future__ import annotations

from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.models import Device
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.transport import DeviceTransport
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
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


def bind_devices(registry: DeviceRegistry, hub: DeviceHub) -> None:
    from lca.layer0_infra.plane.machine import (
        set_machine_resolver,
        set_machine_transport_resolver,
    )

    def _resolve(device_id: str | None) -> PlaneRef | None:
        device = registry.select_online(device_id)
        if device is None:
            return None
        return plane_ref_for_device(device)

    def _transport(device_id: str) -> DeviceTransport | None:
        return DeviceTransport.for_device(registry, hub, device_id)

    set_machine_resolver(_resolve)
    set_machine_transport_resolver(_transport)
