"""GuestLayout ownership: one image contract, one value object."""

from __future__ import annotations

import shlex

from lca.contracts.models.core.guest_layout import GuestLayout, join_under, outputs_under
from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT, SANDBOX_OUTPUT_SUBDIR
from lca.infrastructure.runtime_plane.resolve import make_sandbox_ref
from lca.infrastructure.sandbox.paths import ONLYBOXES


def test_outputs_under_is_the_join_rule() -> None:
    assert outputs_under("/home/sandbox-user") == "/home/sandbox-user/outputs"
    assert outputs_under("/mnt/data") == f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}"
    assert join_under("/home/u", ".lca") == "/home/u/.lca"


def test_onlyboxes_layout_reads_image_contract() -> None:
    assert ONLYBOXES.root == SANDBOX_MOUNT_ROOT
    assert ONLYBOXES.outputs_dir == outputs_under(SANDBOX_MOUNT_ROOT)
    assert ONLYBOXES.init_marker.startswith(SANDBOX_MOUNT_ROOT)
    assert ONLYBOXES.join("outputs", "a.pptx") == join_under(
        SANDBOX_MOUNT_ROOT, "outputs", "a.pptx"
    )
    assert ONLYBOXES.attachment_path("../x.csv") == join_under(SANDBOX_MOUNT_ROOT, "x.csv")
    assert ONLYBOXES.output_file("deck.pptx") == join_under(ONLYBOXES.outputs_dir, "deck.pptx")


def test_sandbox_plane_factory_uses_layout() -> None:
    plane = make_sandbox_ref()
    assert plane.root == ONLYBOXES.root
    assert plane.outputs_dir == ONLYBOXES.outputs_dir
    assert plane.outputs_dir == outputs_under(plane.root)


def test_from_root_is_how_a_future_adapter_varies() -> None:
    other = GuestLayout.from_root("/workspace")
    assert other.root == "/workspace"
    assert other.outputs_dir == "/workspace/outputs"
    assert other.with_cwd("ls") == f"cd {shlex.quote('/workspace')} && ls"


def test_cwd_wrap_enables_relative_outputs() -> None:
    wrapped = ONLYBOXES.with_cwd("officecli create outputs/a.pptx --json")
    assert wrapped == (
        f"cd {shlex.quote(SANDBOX_MOUNT_ROOT)} && officecli create outputs/a.pptx --json"
    )
