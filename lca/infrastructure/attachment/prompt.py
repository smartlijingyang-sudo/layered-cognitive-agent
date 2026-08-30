"""Uploaded-file paths for prompts — LobeHub ``uploadedFiles.ts`` parity.

Staging (``stage_payload`` / sandbox mount) and agent prompts MUST resolve
paths through this module so bootstrap and instructions never drift.
"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.models.core.plane import PlaneKind
from lca.contracts.models.core.sandbox import (
    SANDBOX_INIT_MAX_FILE_BYTES,
    SANDBOX_INIT_MAX_FILES,
)
from lca.infrastructure.attachment.layout import AttachmentLayout, sanitize_attachment_name
from lca.infrastructure.attachment.settings import get_attachment_policy
from lca.infrastructure.file_store import FileStore, LocalFileStore
from lca.infrastructure.sandbox.paths import ONLYBOXES
from lca.infrastructure.tools.run_attachment_scope import get_current_run_attachment_ids
from lca.infrastructure.tools.run_finalizer import get_current_run_id

_BYTE_UNITS = ("B", "KB", "MB", "GB")


def _format_bytes(size: int | None) -> str:
    if size is None or size <= 0:
        return ""
    value = float(size)
    unit = 0
    while value >= 1024 and unit < len(_BYTE_UNITS) - 1:
        value /= 1024
        unit += 1
    rounded = int(value) if unit == 0 else round(value, 1)
    return f" ({rounded}{_BYTE_UNITS[unit]})"


def select_attachment_init_files(
    files: Sequence[tuple[str, int | None]],
) -> list[tuple[str, int | None]]:
    """Apply LobeHub size/count caps — shared by bootstrap and prompt."""
    eligible = [
        (name, size) for name, size in files if size is None or size <= SANDBOX_INIT_MAX_FILE_BYTES
    ]
    return eligible[:SANDBOX_INIT_MAX_FILES]


def sandbox_attachment_path(name: str) -> str:
    """Absolute guest path for a sandbox-uploaded file (``/mnt/data/<basename>``)."""
    return ONLYBOXES.attachment_path(sanitize_attachment_name(name))


def resolve_machine_attachment_paths(
    root: str,
    run_id: str,
    attachment_ids: Sequence[str],
    store: FileStore,
    *,
    layout: AttachmentLayout | None = None,
) -> list[tuple[str, int | None]]:
    """Ordered ``(absolute_path, size)`` pairs for this run's staged inbox copies."""
    active_layout = layout if layout is not None else AttachmentLayout()
    paths: list[tuple[str, int | None]] = []
    seen: set[str] = set()
    for raw_id in attachment_ids:
        attachment_id = str(raw_id).strip()
        if not attachment_id or attachment_id in seen:
            continue
        meta = store.get(attachment_id)
        if meta is None:
            continue
        seen.add(attachment_id)
        path = active_layout.absolute_file(root, run_id, meta.name)
        paths.append((path, meta.size_bytes))
    return paths


def resolve_sandbox_attachment_paths(
    attachment_ids: Sequence[str],
    store: FileStore,
) -> list[tuple[str, int | None]]:
    """Ordered ``(guest_path, size)`` pairs for sandbox session copies."""
    meta_rows: list[tuple[str, int | None]] = []
    for attachment_id in attachment_ids:
        meta = store.get(str(attachment_id).strip())
        if meta is None:
            continue
        meta_rows.append((meta.name, meta.size_bytes))

    seen: set[str] = set()
    paths: list[tuple[str, int | None]] = []
    for name, size in select_attachment_init_files(meta_rows):
        path = sandbox_attachment_path(name)
        if path in seen:
            continue
        seen.add(path)
        paths.append((path, size))
    return paths


def format_uploaded_files_list(
    paths: Sequence[tuple[str, int | None]],
    *,
    header: str,
) -> str:
    """Render bullet list; empty string when there are no paths."""
    if not paths:
        return ""
    lines = [f"- {path}{_format_bytes(size)}" for path, size in paths]
    header_text = header.strip()
    if not header_text:
        return "\n".join(lines)
    return f"{header_text}\n" + "\n".join(lines)


def format_machine_uploaded_files_prompt(
    root: str,
    run_id: str,
    attachment_ids: Sequence[str],
    store: FileStore,
) -> str:
    """Dynamic list for ``machine_system_role`` ``{{uploaded_files}}``."""
    policy = get_attachment_policy()
    paths = resolve_machine_attachment_paths(root, run_id, attachment_ids, store)
    return format_uploaded_files_list(
        paths,
        header=policy.machine_uploaded_files_list_header,
    )


def format_sandbox_uploaded_files_prompt(
    store: FileStore,
    attachment_ids: Sequence[str],
) -> str:
    """Dynamic list for cloud sandbox ``{{sandbox_uploaded_files}}``."""
    policy = get_attachment_policy()
    paths = resolve_sandbox_attachment_paths(attachment_ids, store)
    return format_uploaded_files_list(
        paths,
        header=policy.sandbox_uploaded_files_list_header,
    )


def render_dsh_workspace_context(
    root: str,
    run_id: str,
    attachment_ids: Sequence[str],
    store: FileStore,
) -> str:
    """Machine-plane workspace block for DSH harness system prompt."""
    policy = get_attachment_policy()
    file_list = format_machine_uploaded_files_prompt(root, run_id, attachment_ids, store)
    if not file_list:
        return ""
    return f"<uploaded_files>\n{policy.machine_policy_text()}\n\n{file_list}\n</uploaded_files>"


def format_skill_attachment_block(store: FileStore | None = None) -> str:
    """Same staged paths as system role — injected on ``activate_skill``."""
    ids = get_current_run_attachment_ids()
    if not ids:
        return ""

    run_id = get_current_run_id().strip()
    if not run_id:
        return ""

    from lca.infrastructure.runtime_plane.machine import resolve_machine
    from lca.infrastructure.runtime_plane.resolve import ref_of, sandbox_ref_from
    from lca.infrastructure.runtime_plane.scope import current_bindings
    from lca.infrastructure.sandbox.factory import resolve_sandbox

    bindings = current_bindings()
    machine = ref_of(bindings, PlaneKind.MACHINE) if bindings is not None else None
    if machine is None:
        machine = resolve_machine()

    store = store if store is not None else LocalFileStore()
    policy = get_attachment_policy()

    if machine is not None and (machine.root or "").strip():
        file_list = format_machine_uploaded_files_prompt(
            machine.root,
            run_id,
            ids,
            store,
        )
        if not file_list:
            return ""
        return (
            "Attachments for this run (use these exact paths; not bare filenames at working root):\n"
            f"{file_list}"
        )

    sandbox = resolve_sandbox()
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    root = (sandbox_ref.root if sandbox_ref is not None else ONLYBOXES.root).strip()
    if not root:
        return ""

    file_list = format_sandbox_uploaded_files_prompt(store, ids)
    if not file_list:
        return ""
    intro = policy.sandbox_policy_text(root)
    return f"{intro}\n\n{file_list}"


def machine_uploaded_files_for_ambient(root: str) -> str:
    """Resolve staged paths from ambient run + attachment scopes."""
    ids = get_current_run_attachment_ids()
    run_id = get_current_run_id().strip()
    if not ids or not run_id or not root.strip():
        return ""
    return format_machine_uploaded_files_prompt(
        root.strip(),
        run_id,
        ids,
        LocalFileStore(),
    )
