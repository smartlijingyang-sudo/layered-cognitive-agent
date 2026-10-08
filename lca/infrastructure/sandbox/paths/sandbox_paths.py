"""Single-seam guest<->host path mapping for sandboxes (todo-81).

The agent sees exactly one filesystem namespace: its own directory, named
``/mnt/data`` (the retained virtual mount name; ADR-0046). The host layout
(session directories, planes, mounts) is runtime-private. This module is the
only place that translates between the two views:

- ``SandboxPaths.resolve(agent_path)``: guest -> host (execution side).
- ``SandboxPaths.present(host_path)``: host -> guest (observation side).
- ``SandboxPaths.rewrite_command(command)``: token-aware guest -> host
  rewriting inside shell command text.
- ``SandboxPaths.present_text(text)``: boundary-aware host -> guest
  projection inside output text.

Plane policy lives in the factory constructors (``for_local`` for the
virtualized Local plane, ``identity`` for Onlyboxes where guest paths are
host paths). Call sites never branch on planes and never repeat the mount
literal. Adding a new execution environment = a new factory constructor;
the agent-visible contract does not move.

Invariants are pinned by
``tests/infrastructure/sandbox/test_sandbox_paths.py``: round-trip
(``present(resolve(p)) == p``), containment (``resolve`` never escapes the
session host root — fail-closed), totality (paths outside the guest
namespace raise instead of passing through silently).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from lca.contracts.models.core.execution.sandbox import SANDBOX_MOUNT_ROOT


class UnresolvableAgentPathError(ValueError):
    """An agent path is outside the guest namespace (totality).

    The agent's namespace is exactly the guest mount; anything else is a
    caller bug. Raised instead of silently passing the path through, which
    would let host paths leak across the sandbox boundary.
    """


class PathEscapeError(ValueError):
    """A guest path resolves outside the session host root (containment).

    Fail-closed: refuse loudly instead of reading/writing outside the
    session's directory.
    """


@dataclass(frozen=True)
class SandboxPaths:
    """Bidirectional guest<->host path mapping, built once per session.

    ``guest_mount`` is the agent-visible root (always POSIX, always
    absolute). ``host_root`` is the real directory backing it on this
    machine (absolute, normalized). The pair is the whole mapping: every
    boundary crossing in the sandbox derives from it.

    ``mounted``: the guest mount is a real kernel bind mount (per-exec
    mount namespace, todo-81 (c)). Text-level translation
    (``rewrite_command``/``present_text``) becomes identity — the kernel
    performs it; path-level ``resolve``/``present`` still map for
    host-side operations.
    """

    guest_mount: str
    host_root: Path
    mounted: bool = False

    def __post_init__(self) -> None:
        mount = self.guest_mount.replace("\\", "/").rstrip("/") or "/"
        if not mount.startswith("/"):
            raise ValueError(f"guest_mount must be an absolute POSIX path: {self.guest_mount!r}")
        object.__setattr__(self, "guest_mount", mount)
        root = Path(os.path.normpath(str(self.host_root)))
        if not root.is_absolute():
            raise ValueError(f"host_root must be absolute: {self.host_root!r}")
        object.__setattr__(self, "host_root", root)

    # ------------------------------------------------------------------
    # factories: plane policy lives here and only here
    # ------------------------------------------------------------------

    @classmethod
    def for_local(
        cls,
        host_root: str | Path,
        *,
        guest_mount: str = SANDBOX_MOUNT_ROOT,
        mounted: bool = False,
    ) -> SandboxPaths:
        """Local plane: the agent's guest mount is backed by a per-session
        host directory (the agent's own assistant directory).

        ``mounted=True`` selects the per-exec mount-namespace mode
        (todo-81 (c)): the guest mount is bind-mounted by the kernel, so
        text-level translation becomes identity.
        """
        return cls(guest_mount=guest_mount, host_root=Path(host_root), mounted=mounted)

    @classmethod
    def identity(cls, *, guest_mount: str = SANDBOX_MOUNT_ROOT) -> SandboxPaths:
        """Identity mapping: guest paths ARE host paths.

        Onlyboxes plane — the container really mounts the guest mount, so
        there is nothing to translate.
        """
        return cls(guest_mount=guest_mount, host_root=Path(guest_mount))

    # ------------------------------------------------------------------
    # core mapping
    # ------------------------------------------------------------------

    def _relative(self, agent_path: str) -> PurePosixPath:
        """Guest path -> path relative to the guest mount (totality gate)."""
        posix = PurePosixPath(agent_path.replace("\\", "/"))
        mount = PurePosixPath(self.guest_mount)
        if posix != mount and mount not in posix.parents:
            raise UnresolvableAgentPathError(
                f"agent path outside guest namespace {self.guest_mount!r}: {agent_path!r}"
            )
        return posix.relative_to(mount)

    def resolve(self, agent_path: str) -> Path:
        """Map a guest path onto the host (execution side).

        Raises :class:`UnresolvableAgentPathError` for paths outside the
        guest namespace and :class:`PathEscapeError` when the result would
        escape the session host root. Never silently passes through.
        """
        rel = self._relative(agent_path)
        candidate = self.host_root.joinpath(*rel.parts)
        # Lexical containment (fail-closed): normpath collapses `.`/`..`
        # without touching the filesystem, so not-yet-existing staging
        # targets are still checked.
        normalized = Path(os.path.normpath(candidate))
        if normalized != self.host_root and self.host_root not in normalized.parents:
            raise PathEscapeError(
                f"agent path escapes session host root {self.host_root}: {agent_path!r}"
            )
        return normalized

    def present(self, host_path: str | Path) -> str:
        """Map a host path back onto the guest view (observation side).

        Paths outside the session host root are returned unchanged: they are
        not part of this session's namespace (matches the historical
        adapter-exit behavior of leaving non-matching text alone).
        """
        text = os.path.normpath(str(host_path))
        if text == str(self.host_root):
            return self.guest_mount
        try:
            rel = Path(text).relative_to(self.host_root)
        except ValueError:
            return str(host_path)
        return f"{self.guest_mount}/{rel.as_posix()}"

    # ------------------------------------------------------------------
    # text-level adapters (command / output boundaries)
    # ------------------------------------------------------------------

    def _is_identity(self) -> bool:
        return str(self.host_root) == self.guest_mount

    def rewrite_command(self, command: str) -> str:
        """Rewrite guest-mount references inside shell command text.

        Token-aware: only occurrences that start a path token are rewritten
        (boundary-aware on both sides). This replaces the old blind
        ``command.replace(mount, root)``, which also rewrote longer tokens
        merely containing the mount as a substring (``/mnt/data2`` ->
        ``<root>2``).

        Mounted mode (real bind mount, todo-81 (c)): identity — the guest
        mount really is the host directory inside the exec namespace, so
        the kernel translates; string rewriting would map an
        already-correct path.
        """
        if not command or self._is_identity() or self.mounted:
            return command
        before = r"(?:^|(?<=[\s\"'`=:;|&<>(){}\[\],]))"
        after = r"(?![A-Za-z0-9_.\-])"
        host = str(self.host_root)
        return re.sub(before + re.escape(self.guest_mount) + after, lambda _: host, command)

    def present_text(self, text: str) -> str:
        """Project host session-root paths in TEXT back to the guest view.

        Boundary-aware (same rule as the historical adapter exit): the host
        root is only replaced when not followed by a path-continuation
        character, so sibling paths that merely share the prefix are left
        alone.

        Mounted mode: identity — guest outputs already name the real guest
        mount; there is no host path to project back.
        """
        if not text or self._is_identity() or self.mounted:
            return text
        return re.sub(
            re.escape(str(self.host_root)) + r"(?![A-Za-z0-9_.\-])",
            lambda _: self.guest_mount,
            text,
        )
