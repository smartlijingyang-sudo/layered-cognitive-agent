"""Environment providers — one adapter per environment source."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.environment.model import (
    EnvironmentKind,
    ExecutionEnvironment,
    environment_from_plane,
)
from lca.contracts.models.core.state.plane import PlaneRef


class SandboxEnvironmentProvider:
    """Project the current cloud sandbox plane as one environment."""

    def __init__(self, plane: PlaneRef) -> None:
        if plane.kind.value != EnvironmentKind.SANDBOX.value:
            raise ValueError(
                f"SandboxEnvironmentProvider requires a sandbox plane, got {plane.kind}"
            )
        self._plane = plane

    def list_environments(self) -> list[ExecutionEnvironment]:
        return [environment_from_plane(self._plane)]


class DeviceEnvironmentProvider:
    """Map every paired device in the registry to a machine environment."""

    def __init__(self, devices: Any | None = None) -> None:
        # Accepts a DeviceProvider (runtime-checkable Protocol) or None.
        self._devices = devices

    def list_environments(self) -> list[ExecutionEnvironment]:
        if self._devices is None:
            return []
        list_fn = getattr(self._devices, "list_devices", None)
        if list_fn is None:
            return []
        envs: list[ExecutionEnvironment] = []
        for device in list_fn():
            if not isinstance(device, dict):
                continue
            device_id = device.get("deviceId") or ""
            if not device_id:
                continue
            envs.append(
                ExecutionEnvironment(
                    kind=EnvironmentKind.MACHINE,
                    id=device_id,
                    label=device.get("hostname") or device_id,
                    platform=device.get("platform", ""),
                    online=bool(device.get("online")),
                    home=device.get("home", ""),
                    workspace=device.get("workspace", ""),
                    metadata=device,
                )
            )
        return envs


__all__ = ["DeviceEnvironmentProvider", "SandboxEnvironmentProvider"]
