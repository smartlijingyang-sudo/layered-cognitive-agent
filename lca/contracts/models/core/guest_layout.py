"""Sandbox guest disk layout — frozen value object, no I/O.

``SANDBOX_MOUNT_ROOT`` is the Onlyboxes / LobeHub image contract.
``GuestLayout.onlyboxes()`` is the only constructor that reads it.
Machine paths never go through this type; they live on ``PlaneRef``.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT, SANDBOX_OUTPUT_SUBDIR

_BACKGROUND_PARTS = (".lca", "background")
_INIT_MARKER_NAME = ".lobe-files-initialized"


def join_under(root: str, *parts: str) -> str:
    extra = "/".join(segment.strip("/\\") for segment in parts if segment)
    base = root.rstrip("/\\")
    return f"{base}/{extra}" if extra else base


def outputs_under(root: str) -> str:
    return join_under(root, SANDBOX_OUTPUT_SUBDIR)


@dataclass(frozen=True)
class GuestLayout:
    root: str
    outputs_dir: str
    background_dir: str
    init_marker: str

    @classmethod
    def from_root(cls, root: str) -> GuestLayout:
        return cls(
            root=root,
            outputs_dir=outputs_under(root),
            background_dir=join_under(root, *_BACKGROUND_PARTS),
            init_marker=join_under(root, _INIT_MARKER_NAME),
        )

    @classmethod
    def onlyboxes(cls) -> GuestLayout:
        return cls.from_root(SANDBOX_MOUNT_ROOT)

    def join(self, *parts: str) -> str:
        return join_under(self.root, *parts)

    def attachment_path(self, name: str) -> str:
        cleaned = name.replace("\\", "/").strip().lstrip("/")
        bits = [part for part in cleaned.split("/") if part and part not in {".", ".."}]
        return self.join(bits[-1] if bits else "file")

    def output_file(self, name: str) -> str:
        return join_under(self.outputs_dir, name)

    def with_cwd(self, command: str) -> str:
        return f"cd {shlex.quote(self.root)} && {command}"
