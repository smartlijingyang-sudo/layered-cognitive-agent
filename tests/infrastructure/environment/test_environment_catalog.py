"""Environment catalog tests — providers, dedup, current marking, factory."""

from __future__ import annotations

from types import SimpleNamespace

from lca.contracts.models.core.environment.model import (
    EnvironmentKind,
    ExecutionEnvironment,
)
from lca.contracts.models.core.state.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.infrastructure.environment.catalog import CompositeEnvironmentCatalog
from lca.infrastructure.environment.factory import build_environment_catalog
from lca.infrastructure.environment.providers import (
    DeviceEnvironmentProvider,
    SandboxEnvironmentProvider,
)


def _sandbox_plane() -> PlaneRef:
    return PlaneRef(
        id="onlyboxes",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
        platform="linux",
    )


class _DeviceSource:
    def __init__(self, devices: list[dict]) -> None:
        self._devices = devices

    def list_devices(self) -> list[dict]:
        return self._devices


def test_sandbox_provider_projects_one_environment() -> None:
    provider = SandboxEnvironmentProvider(_sandbox_plane())
    envs = provider.list_environments()
    assert len(envs) == 1
    assert envs[0].kind is EnvironmentKind.SANDBOX
    assert envs[0].id == "onlyboxes"
    assert envs[0].root == "/mnt/data"
    assert envs[0].online is True


def test_device_provider_maps_registry_rows() -> None:
    source = _DeviceSource(
        [
            {
                "deviceId": "m-lipcmain",
                "hostname": "lipcmain",
                "platform": "Windows",
                "home": "C:\\Users\\li",
                "workspace": "F:\\下载",
                "online": True,
                "capabilities": ["read_file", "write_file", "run_command"],
            },
            {
                "deviceId": "m-desktop",
                "hostname": "DESKTOP-X",
                "platform": "Windows",
                "home": "C:\\Users\\x",
                "workspace": "C:\\Users\\x",
                "online": False,
            },
        ]
    )
    envs = DeviceEnvironmentProvider(source).list_environments()
    assert [e.id for e in envs] == ["m-lipcmain", "m-desktop"]
    assert envs[0].kind is EnvironmentKind.MACHINE
    assert envs[0].label == "lipcmain"
    assert envs[0].online is True
    assert envs[0].workspace == "F:\\下载"
    assert envs[0].root == "F:\\下载"
    assert envs[0].outputs_dir == "F:\\下载/outputs"
    assert envs[0].capabilities == ("read_file", "write_file", "run_command")
    assert envs[1].online is False


def test_device_provider_handles_none_source() -> None:
    assert DeviceEnvironmentProvider(None).list_environments() == []


def test_catalog_dedups_and_marks_current() -> None:
    sandbox = SandboxEnvironmentProvider(_sandbox_plane())
    source = _DeviceSource(
        [
            {
                "deviceId": "m-lipcmain",
                "hostname": "lipcmain",
                "platform": "Windows",
                "home": "C:\\Users\\li",
                "workspace": "F:\\下载",
                "online": True,
            }
        ]
    )
    current = ExecutionEnvironment(
        kind=EnvironmentKind.MACHINE,
        id="m-lipcmain",
        label="lipcmain",
        platform="Windows",
        online=True,
        is_current=True,
    )
    catalog = CompositeEnvironmentCatalog(
        [sandbox, DeviceEnvironmentProvider(source)],
        current=current,
    )
    envs = catalog.list_all()
    by_id = {env.id: env for env in envs}
    assert set(by_id) == {"onlyboxes", "m-lipcmain"}
    assert by_id["m-lipcmain"].is_current is True
    assert by_id["onlyboxes"].is_current is False
    assert catalog.current() is current


def test_catalog_includes_current_when_provider_missing() -> None:
    current = ExecutionEnvironment(
        kind=EnvironmentKind.SANDBOX,
        id="onlyboxes",
        label="Onlyboxes",
        platform="linux",
        online=True,
        is_current=True,
    )
    catalog = CompositeEnvironmentCatalog([], current=current)
    envs = catalog.list_all()
    assert len(envs) == 1
    assert envs[0].id == "onlyboxes"
    assert envs[0].is_current is True


def test_build_environment_catalog_wires_plane_and_devices() -> None:
    machine = PlaneRef(
        id="m-lipcmain",
        label="lipcmain",
        kind=PlaneKind.MACHINE,
        root="F:\\下载",
        outputs_dir="F:\\下载\\outputs",
        platform="Windows",
        home="C:\\Users\\li",
    )
    resolver = SimpleNamespace(
        list_devices=lambda: [
            {
                "deviceId": "m-lipcmain",
                "hostname": "lipcmain",
                "platform": "Windows",
                "home": "C:\\Users\\li",
                "workspace": "F:\\下载",
                "online": True,
            }
        ]
    )
    catalog = build_environment_catalog(
        PlaneBindings(primary=machine),
        machine_resolver=resolver,  # type: ignore[arg-type]
    )
    envs = catalog.list_all()
    current = catalog.current()
    assert current is not None and current.id == "m-lipcmain" and current.is_current is True
    assert {env.id for env in envs} == {"m-lipcmain"}
    assert envs[0].is_current is True
