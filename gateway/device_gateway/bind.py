"""Application-scoped device-to-machine resolution."""

from __future__ import annotations

from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.models import Device
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.transport import DeviceTransport
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.protocols.infra import MachineResolver, MachineTransport
from lca.infrastructure.plane.paths import outputs_under
from lca.infrastructure.sandbox.host_settings import load_host_settings


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


_hub: DeviceHub | None = None


def device_hub() -> DeviceHub | None:
    """Bound device hub (gateway process). Used by DSH streaming runtime.

    Branch-side helper preserved for the soft-locked ``gateway/runs/loop_drivers.py``
    which calls ``execute_dsh_session`` from the restored ``gateway/runs/dsh_execute.py``.
    The DSH runtime needs access to the active DeviceHub to issue
    StreamEvents on the right hub. Main refactored this away; the branch
    keeps it because the loop_drivers soft-lock surface still references
    DSH execution paths.
    """
    return _hub


def bind_devices(registry: DeviceRegistry, hub: DeviceHub) -> None:
    """Branch-side helper preserved for the soft-locked ``gateway/app.py``.

    Wires the on-device registry + hub into the global machine resolver and
    transport resolver used by layer0 plane layer (main refactored this
    out; the branch keeps it because ``gateway/app.py:235`` is a
    soft-lock surface per ADR-0103 §2 and calls ``bind_devices`` directly).
    """
    global _hub
    _hub = hub

    from lca.infrastructure.plane.machine import (
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


__all__ = ["DeviceMachineResolver", "bind_devices", "plane_ref_for_device"]
