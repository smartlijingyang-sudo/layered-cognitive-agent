"""Gateway Presence → machine PlaneRef + transport."""

from __future__ import annotations

from gateway.host_sandbox import HostSandbox
from gateway.presence.models import CAP_SANDBOX, Device
from gateway.presence.registry import PresenceRegistry
from gateway.presence.rpc import ExecHub
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.layer0_infra.sandbox.host_settings import load_host_settings


def select_machine_device(
    presence: PresenceRegistry,
    device_id: str | None,
) -> Device | None:
    online = presence.online_with(CAP_SANDBOX)
    if device_id:
        for device in online:
            if device.device_id == device_id:
                return device
        return None
    if len(online) == 1:
        return online[0]
    if presence.last_success_id:
        for device in online:
            if device.device_id == presence.last_success_id:
                return device
    return None


def plane_ref_for_device(device: Device) -> PlaneRef:
    settings = load_host_settings()
    root = device.root.strip() or str(settings.workspace())
    outputs = f"{root.rstrip('/')}/outputs"
    return PlaneRef(
        id=device.device_id,
        label=device.name or device.device_id,
        kind=PlaneKind.MACHINE,
        root=root,
        outputs_dir=outputs,
        platform=device.platform,
        home=device.home,
    )


def bind_presence(
    presence: PresenceRegistry,
    hub: ExecHub,
) -> None:
    from lca.layer0_infra.plane.machine import (
        set_machine_resolver,
        set_machine_transport_resolver,
    )

    def _resolve(device_id: str | None) -> PlaneRef | None:
        device = select_machine_device(presence, device_id)
        if device is None:
            return None
        presence.remember_success(device.device_id)
        return plane_ref_for_device(device)

    def _transport(device_id: str) -> HostSandbox | None:
        return HostSandbox.for_device(presence, hub, device_id)

    set_machine_resolver(_resolve)
    set_machine_transport_resolver(_transport)
