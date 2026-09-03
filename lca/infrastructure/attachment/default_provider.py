"""Default FileRef provider — one place, three seams (ADR-0121 PR-B).

Owns the contract between :mod:`lca.infrastructure.file_store` and the
attachment Protocol seams. Replaces the previous scattered
``format_*`` / ``compose_question`` / ``stage_payload`` /
``listed_paths`` / ``render_*`` helpers (see ADR-0121 §3 dead-code list).

Design choices:

  * **One renderer, three blocks.** All prompt text comes out of
    :class:`DefaultAttachmentPromptRenderer`. No more "format_skill_attachment_block
    duplicates the system-role policy text".
  * **Plane-resolved ``process_path``.** :meth:`DefaultAttachmentResolver.resolve_for_plane`
    is the single source of truth for translating ``display_path`` →
    ``process_path`` per plane; both sandbox and machine share one rule book.
  * **Inline content guarded once.** :meth:`DefaultAttachmentPromptRenderer.inline_content_block`
    enforces the policy ``inline_max_bytes`` / mime / name rules so callers
    never have to.
"""

from __future__ import annotations

import html
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from lca.contracts.models.core.file_ref import FileRef, FileRefKind
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.models.core.sandbox import (
    SANDBOX_MOUNT_ROOT,
    MountEntry,
    MountManifest,
)
from lca.contracts.protocols.runtime.attachment import (
    ResolvedAttachment,
)
from lca.contracts.protocols.runtime.attachment_errors import (
    AttachmentError,
    AttachmentErrorCode,
)
from lca.infrastructure.attachment.layout import (
    AttachmentLayout,
    sanitize_attachment_name,
)
from lca.infrastructure.attachment.normalizer import normalize_for_injection
from lca.infrastructure.attachment.settings import (
    AttachmentPolicyDocument,
    get_attachment_policy,
)
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.sandbox.paths import ONLYBOXES

if TYPE_CHECKING:
    from lca.infrastructure.file_store import StoredFile

_PROVIDER_LABEL = "lca-attachment-default"


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DefaultAttachmentResolver:
    """Map ``attachment_id`` → :class:`FileRef` via :class:`FileStore`."""

    store: FileStore
    policy: AttachmentPolicyDocument | None = None
    label: str = _PROVIDER_LABEL + ".resolver"

    def _policy(self) -> AttachmentPolicyDocument:
        return self.policy or get_attachment_policy()

    def resolve(self, attachment_ids: Sequence[str]) -> tuple[ResolvedAttachment, ...]:
        out: list[ResolvedAttachment] = []
        seen: set[str] = set()
        for raw_id in attachment_ids:
            aid = str(raw_id).strip()
            if not aid or aid in seen:
                continue
            stored = self.store.get(aid)
            if stored is None:
                raise AttachmentError(
                    AttachmentErrorCode.MISSING_ATTACHMENT,
                    f"unknown attachment_id={aid!r}",
                    context={"attachment_id": aid},
                )
            seen.add(aid)
            inline = self._maybe_inline(stored)
            out.append(
                ResolvedAttachment(
                    ref=FileRef(
                        kind="user_upload",
                        target_key=aid,
                        display_path=stored.name,
                        process_path=stored.name,
                        file_url=stored.url,
                        mime_type=stored.mime_type,
                        size_bytes=max(stored.size_bytes, 0),
                        source="lobehub_upload",
                        attachment_id=aid,
                    ),
                    inline_content=inline,
                )
            )
        return tuple(out)

    def resolve_for_plane(self, ref: FileRef, plane: PlaneRef | None) -> FileRef:
        if plane is None:
            return ref
        if plane.kind is PlaneKind.SANDBOX:
            new_process = _sandbox_path(ref.display_path)
        else:
            new_process = _machine_path(ref)
        new_kind: FileRefKind = (
            "sandbox_init" if plane.kind is PlaneKind.SANDBOX else "inbox_staged"
        )
        return FileRef(
            kind=new_kind,
            target_key=ref.target_key,
            display_path=ref.display_path,
            process_path=new_process,
            file_url=ref.file_url,
            mime_type=ref.mime_type,
            size_bytes=ref.size_bytes,
            source=ref.source,
            attachment_id=ref.attachment_id,
        )

    def _maybe_inline(self, stored: StoredFile) -> str | None:
        policy = self._policy()
        if not policy.allows_inline(stored.mime_type, stored.name):
            return None
        data = self.store.read_bytes(stored.attachment_id)
        if data is None or len(data) > policy.inline_max_bytes:
            return None
        try:
            return normalize_for_injection(data.decode("utf-8", errors="replace"))
        except Exception:
            # INTENTIONAL: 二进制 / 非 utf-8 附件解码失败 → 回 None,让上层
            # 走原始字节旁路;附件是辅助通道,不阻断主 prompt 流程。
            return None


def _sandbox_path(display_path: str) -> str:
    cleaned = sanitize_attachment_name(display_path)
    if cleaned == "file":
        return f"{SANDBOX_MOUNT_ROOT}/file"
    return f"{SANDBOX_MOUNT_ROOT}/{cleaned}"


def _machine_path(ref: FileRef) -> str:
    if ref.attachment_id is None:
        return sanitize_attachment_name(ref.display_path)
    layout = AttachmentLayout(get_attachment_policy())
    run_id = _current_run_segment()
    return layout.absolute_file(_machine_root(), run_id, ref.display_path)


def _machine_root() -> str:
    from lca.infrastructure.attachment.run_machine_root_scope import (
        get_current_machine_root,
    )
    from lca.infrastructure.tools.run_finalizer import get_current_run_id

    override = get_current_machine_root()
    if override:
        return override
    if ONLYBOXES.root:
        return ONLYBOXES.root
    _ = get_current_run_id
    return "/workspace"


def _current_run_segment() -> str:
    from lca.infrastructure.tools.run_finalizer import get_current_run_id

    return get_current_run_id().strip() or "unbound"


# ---------------------------------------------------------------------------
# Stager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DefaultAttachmentStager:
    """Push FileRefs into machine inbox / sandbox manifest."""

    resolver: DefaultAttachmentResolver
    label: str = _PROVIDER_LABEL + ".stager"

    def stage_to_machine(
        self,
        *,
        run_id: str,
        refs: Sequence[FileRef],
    ) -> dict[str, str]:
        out: dict[str, str] = {}
        layout = AttachmentLayout(get_attachment_policy())
        for ref in refs:
            if ref.kind != "user_upload":
                continue
            data = self.resolver.store.read_bytes(ref.attachment_id or "")
            if data is None:
                continue
            target = layout.absolute_file(_machine_root(), run_id, ref.display_path)
            _write_atomically(target, data)
            out[ref.target_key] = target
        return out

    def stage_to_sandbox(
        self,
        *,
        sandbox_id: str,
        refs: Sequence[FileRef],
    ) -> tuple[MountEntry, ...]:
        del sandbox_id  # backend-specific; only the resolver decides the path.
        entries: list[MountEntry] = []
        for ref in refs:
            if ref.kind != "user_upload":
                continue
            entries.append(
                MountEntry(
                    path=_sandbox_path(ref.display_path),
                    name=ref.display_path,
                    size_bytes=ref.size_bytes,
                    attachment_id=ref.attachment_id or "",
                )
            )
        return tuple(entries)

    def build_manifest(self, refs: Sequence[FileRef]) -> MountManifest:
        return MountManifest(entries=self.stage_to_sandbox(sandbox_id="", refs=refs))


def _write_atomically(target: str, data: bytes) -> None:
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DefaultAttachmentPromptRenderer:
    """Single renderer for all three attachment blocks.

    Implements :class:`AttachmentPromptRenderer`. Replaces
    ``AttachmentManifest.render`` + ``format_*_uploaded_files_prompt`` +
    ``format_skill_attachment_block`` + ``machine_uploaded_files_for_ambient``.
    """

    resolver: DefaultAttachmentResolver
    policy: AttachmentPolicyDocument | None = None
    label: str = _PROVIDER_LABEL + ".renderer"

    def _policy(self) -> AttachmentPolicyDocument:
        return self.policy or get_attachment_policy()

    def identity_block(self, refs: Sequence[FileRef]) -> str:
        if not refs:
            return ""
        policy = self._policy()
        body = "\n".join(self._identity_line(ref) for ref in refs)
        return (
            f"{policy.system_context_open}\n"
            f"<context.instruction>{html.escape(policy.files_instruction)}</context.instruction>\n"
            f"<files_info>\n"
            f"<files>\n"
            f"<files_docstring>here are user upload files you can refer to</files_docstring>\n"
            f"{body}\n"
            f"</files>\n"
            f"</files_info>\n"
            f"{policy.system_context_close}"
        )

    def guest_path_block(self, refs: Sequence[FileRef], plane: PlaneRef | None) -> str:
        if not refs:
            return ""
        policy = self._policy()
        resolved = (
            tuple(self.resolver.resolve_for_plane(r, plane) for r in refs)
            if plane is not None
            else tuple(refs)
        )
        header = (
            policy.machine_uploaded_files_list_header
            if plane is None or plane.kind is PlaneKind.MACHINE
            else policy.sandbox_uploaded_files_list_header
        )
        body = "\n".join(
            f"- {html.escape(r.process_path)}{self._fmt_bytes(r.size_bytes)}" for r in resolved
        )
        return f"<uploaded_files>\n{header}\n{body}\n</uploaded_files>"

    def inline_content_block(self, refs: Sequence[FileRef]) -> str:
        out: list[str] = []
        for ref in refs:
            inline = self._inline_text(ref)
            if inline is None:
                continue
            out.append(self._identity_line(ref, content=inline))
        return "\n".join(out)

    # --- internals ---------------------------------------------------------

    def _identity_line(self, ref: FileRef, *, content: str | None = None) -> str:
        attrs = (
            f'id="{html.escape(ref.target_key, quote=True)}" '
            f'name="{html.escape(ref.display_path, quote=True)}" '
            f'type="{html.escape(ref.mime_type, quote=True)}" '
            f'size="{ref.size_bytes}" '
            f'url="{html.escape(ref.file_url, quote=True)}"'
        )
        body = content if content is not None else ""
        if body:
            return f"<file {attrs}>{html.escape(body)}</file>"
        return f"<file {attrs}></file>"

    def _fmt_bytes(self, size: int) -> str:
        if size <= 0:
            return ""
        value = float(size)
        unit = 0
        units = ("B", "KB", "MB", "GB")
        while value >= 1024 and unit < len(units) - 1:
            value /= 1024
            unit += 1
        rounded = int(value) if unit == 0 else round(value, 1)
        return f" ({rounded}{units[unit]})"

    def _inline_text(self, ref: FileRef) -> str | None:
        if ref.attachment_id is None:
            return None
        policy = self._policy()
        if not policy.allows_inline(ref.mime_type, ref.display_path):
            return None
        data = self.resolver.store.read_bytes(ref.attachment_id)
        if data is None or len(data) > policy.inline_max_bytes:
            return None
        try:
            return normalize_for_injection(data.decode("utf-8", errors="replace"))
        except Exception:
            # INTENTIONAL: 二进制附件 / 编码错误视作"不可注入",回 None 让上层
            # 走原始字节旁路;附件是辅助通道,不阻断主 prompt 流程。
            return None


def install_attachment_default_plugins() -> None:  # pragma: no cover - hook
    """No-op stub; the real registration lives in the plugin loader PR-D."""
    return None


# Module-level convenience used by the existing seam glue:

__all__ = [
    "DefaultAttachmentPromptRenderer",
    "DefaultAttachmentResolver",
    "DefaultAttachmentStager",
]


# Quiet linter complaint about unused import (kept for IDE consumers).
_ = shutil
