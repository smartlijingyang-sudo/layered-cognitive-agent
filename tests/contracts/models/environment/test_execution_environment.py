"""ExecutionEnvironment value-object tests (SSOT for model-visible env facts)."""

from __future__ import annotations

import dataclasses

from lca.contracts.models.core.environment.model import (
    EnvironmentKind,
    ExecutionEnvironment,
    environment_from_plane,
)
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef


def _machine_plane() -> PlaneRef:
    return PlaneRef(
        id="m-lipcmain",
        label="lipcmain",
        kind=PlaneKind.MACHINE,
        root="F:\\下载",
        outputs_dir="F:\\下载\\outputs",
        platform="Windows",
        home="C:\\Users\\li",
    )


def test_value_object_is_frozen() -> None:
    env = ExecutionEnvironment(
        kind=EnvironmentKind.MACHINE,
        id="m-lipcmain",
        label="lipcmain",
        platform="Windows",
        online=True,
    )
    try:
        env.online = False  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("ExecutionEnvironment must be frozen")


def test_environment_from_plane_projects_machine() -> None:
    env = environment_from_plane(_machine_plane(), is_current=True)
    assert env.kind is EnvironmentKind.MACHINE
    assert env.id == "m-lipcmain"
    assert env.label == "lipcmain"
    assert env.platform == "Windows"
    assert env.root == "F:\\下载"
    assert env.outputs_dir == "F:\\下载\\outputs"
    assert env.home == "C:\\Users\\li"
    assert env.is_current is True
    assert env.online is True


def test_environment_from_plane_projects_sandbox() -> None:
    plane = PlaneRef(
        id="onlyboxes",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
        platform="linux",
    )
    env = environment_from_plane(plane)
    assert env.kind is EnvironmentKind.SANDBOX
    assert env.id == "onlyboxes"
    assert env.platform == "linux"
    assert env.root == "/mnt/data"
    assert env.outputs_dir == "/mnt/data/outputs"
    assert env.is_current is False


def test_to_dict_is_stable_wire_shape() -> None:
    env = environment_from_plane(_machine_plane(), is_current=True)
    data = env.to_dict()
    assert data["kind"] == "machine"
    assert data["id"] == "m-lipcmain"
    assert data["label"] == "lipcmain"
    assert data["platform"] == "Windows"
    assert data["online"] is True
    assert data["is_current"] is True
    assert data["root"] == "F:\\下载"
    assert data["outputs_dir"] == "F:\\下载\\outputs"
    assert data["home"] == "C:\\Users\\li"
    assert data["capabilities"] == []
    # metadata must not shadow core fields
    assert data["id"] == "m-lipcmain"
