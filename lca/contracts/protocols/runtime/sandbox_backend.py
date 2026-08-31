"""Sandbox backend seam — the only contract tool dispatch and prompt rendering rely on.

ADR-0121. The default implementation is Onlyboxes; this Protocol is what lets
any sandbox backend (e2b, docker, ssh, in-memory test double) drop in without
the rest of LCA caring.

Implementations MUST:

  * Be idempotent under repeated ``mount_entries`` calls.
  * Never raise on missing guest paths — return ``None`` from ``read_bytes``.
  * Expose a stable ``label`` (used in Journal entries, debug surfaces, and the
    ``attachment.sandbox_backend`` field of the runtime manifest).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.file_ref import FileRef
from lca.contracts.models.core.sandbox import MountManifest


@runtime_checkable
class SandboxBackend(Protocol):
    """Backend-agnostic contract for a run-scoped sandbox.

    Separate from :class:`lca.contracts.protocols.runtime.attachment.SandboxMountAdapter`
    so the mount adapter can stay narrow (no execute semantics) while the
    backend owns the full lifecycle.
    """

    label: str

    def mount_root(self) -> str:
        """Absolute guest path that all FileRefs are anchored under."""
        ...

    def ensure_mounts(self, manifest: MountManifest, *, timeout_s: int) -> MountManifest:
        """Push the manifest to the backend; return what was actually mounted."""
        ...

    def translate_ref(self, ref: FileRef) -> FileRef:
        """Return a new :class:`FileRef` whose ``process_path`` points inside
        this backend's mount root (or unchanged when already correct)."""
        ...

    def read_bytes(self, process_path: str) -> bytes | None:
        """Read raw bytes; return ``None`` if absent (never raise)."""
        ...

    def list_files(self, directory: str) -> Sequence[str]:
        """List absolute guest paths under ``directory``; empty when absent."""
        ...


__all__ = ["SandboxBackend"]
