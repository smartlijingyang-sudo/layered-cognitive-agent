"""Environment providers — one adapter per environment source."""

from __future__ import annotations

from lca.contracts.models.core.environment.model import (
    EnvironmentKind,
    ExecutionEnvironment,
    environment_from_plane,
)
from lca.contracts.models.core.state.plane import PlaneRef
from lca.contracts.protocols.runtime.environment import DeviceProvider


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

    def __init__(self, devices: DeviceProvider | None = None) -> None:
        self._devices = devices

    def list_environments(self) -> list[ExecutionEnvironment]:
        if self._devices is None:
            return []
        return [
            self._from_device(device)
            for device in self._devices.list_devices()
            if isinstance(device, dict) and device.get("deviceId")
        ]

    @staticmethod
    def _from_device(device: dict) -> ExecutionEnvironment:
        device_id = device["deviceId"]
        return ExecutionEnvironment(
            kind=EnvironmentKind.MACHINE,
            id=device_id,
            label=device.get("hostname") or device_id,
            platform=device.get("platform", ""),
            online=bool(device.get("online")),
            home=device.get("home", ""),
            workspace=device.get("workspace", ""),
            metadata=device,
        )


__all__ = ["DeviceEnvironmentProvider", "SandboxEnvironmentProvider"]
