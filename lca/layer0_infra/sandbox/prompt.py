"""Cloud sandbox prompt helpers — LobeHub ``uploadedFiles.ts`` + systemRole parity."""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.models.core.sandbox import (
    SANDBOX_INIT_MAX_FILE_BYTES,
    SANDBOX_INIT_MAX_FILES,
    SANDBOX_MOUNT_ROOT,
)
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.sandbox.bootstrap import sandbox_output_path
from lca.layer0_infra.tools.run_attachment_scope import get_current_run_attachment_ids

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


def _sanitize_guest_basename(name: str) -> str:
    cleaned = name.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return parts[-1] if parts else "file"


def sandbox_uploaded_file_path(name: str) -> str:
    return f"{SANDBOX_MOUNT_ROOT}/{_sanitize_guest_basename(name)}"


def select_sandbox_init_files(
    files: Sequence[tuple[str, int | None]],
) -> list[tuple[str, int | None]]:
    """Apply LobeHub size/count caps — shared by bootstrap and prompt."""
    eligible = [
        (name, size) for name, size in files if size is None or size <= SANDBOX_INIT_MAX_FILE_BYTES
    ]
    return eligible[:SANDBOX_INIT_MAX_FILES]


def format_uploaded_files_prompt(
    store: FileStore,
    attachment_ids: Sequence[str],
) -> str:
    """Render ``{{sandbox_uploaded_files}}`` section for the cloud sandbox system role."""
    meta_rows: list[tuple[str, int | None]] = []
    for attachment_id in attachment_ids:
        meta = store.get(str(attachment_id).strip())
        if meta is None:
            continue
        meta_rows.append((meta.name, meta.size_bytes))

    seen: set[str] = set()
    lines: list[str] = []
    for name, size in select_sandbox_init_files(meta_rows):
        path = sandbox_uploaded_file_path(name)
        if path in seen:
            continue
        seen.add(path)
        lines.append(f"- {path}{_format_bytes(size)}")

    if not lines:
        return ""
    return "These user-uploaded files are pre-loaded and ready to use:\n" + "\n".join(lines)


def render_cloud_sandbox_system_role(
    system_role_template: str,
    *,
    store: FileStore | None = None,
    attachment_ids: Sequence[str] | None = None,
) -> str:
    """Substitute dynamic placeholders in the cloud sandbox system role template."""
    ids = (
        tuple(str(i).strip() for i in attachment_ids if str(i).strip())
        if attachment_ids is not None
        else get_current_run_attachment_ids()
    )
    uploaded = ""
    if store is not None and ids:
        uploaded = format_uploaded_files_prompt(store, ids)

    from lca.layer0_infra.sandbox.surface import current_surface, environment_note

    surface = current_surface()
    outputs_dir = sandbox_output_path()
    rendered = system_role_template.replace("{{sandbox_uploaded_files}}", uploaded)
    rendered = rendered.replace("{{sandbox_outputs_dir}}", outputs_dir)
    if "{{sandbox_environment_note}}" in rendered:
        rendered = rendered.replace("{{sandbox_environment_note}}", environment_note(surface))
    return rendered.strip()
