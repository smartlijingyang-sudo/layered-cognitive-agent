"""Cloud sandbox prompt helpers — LobeHub ``uploadedFiles.ts`` + systemRole parity."""

from __future__ import annotations

from collections.abc import Sequence

from lca.infrastructure.attachment.prompt import (
    format_sandbox_uploaded_files_prompt,
    sandbox_attachment_path,
    select_attachment_init_files,
)
from lca.infrastructure.file_store import FileStore

# ADR-0101 PR-3 carry-over:延迟导入以避开 ``tools`` 包预加载导致的循环
# (见 runtime_mount.py 注释)。

# Backward-compatible aliases — paths resolve through attachment.prompt SSOT.
sandbox_uploaded_file_path = sandbox_attachment_path
select_sandbox_init_files = select_attachment_init_files


def format_uploaded_files_prompt(
    store: FileStore,
    attachment_ids: Sequence[str],
) -> str:
    """Render ``{{sandbox_uploaded_files}}`` section for the cloud sandbox system role."""
    return format_sandbox_uploaded_files_prompt(store, attachment_ids)


def format_machine_uploaded_files_prompt(root: str) -> str:
    """Render ``{{uploaded_files}}`` — run-scoped inbox paths only."""
    from lca.infrastructure.attachment.prompt import machine_uploaded_files_for_ambient

    return machine_uploaded_files_for_ambient(root)


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
        else _current_attachment_ids()
    )
    uploaded = ""
    if store is not None and ids:
        uploaded = format_sandbox_uploaded_files_prompt(store, ids)

    from lca.infrastructure.sandbox.paths import ONLYBOXES
    from lca.infrastructure.sandbox.surface import environment_note

    outputs_dir = ONLYBOXES.outputs_dir
    root = ONLYBOXES.root
    from lca.infrastructure.attachment import get_attachment_policy

    rendered = system_role_template.replace("{{sandbox_uploaded_files}}", uploaded)
    rendered = rendered.replace("{{sandbox_outputs_dir}}", outputs_dir)
    rendered = rendered.replace("{{sandbox_workspace_root}}", root)
    rendered = rendered.replace(
        "{{attachment_policy}}", get_attachment_policy().sandbox_policy_text(root)
    )
    if "{{sandbox_environment_note}}" in rendered:
        rendered = rendered.replace("{{sandbox_environment_note}}", environment_note())
    return rendered.strip()


def _current_attachment_ids() -> tuple[str, ...]:
    """延迟导入 helper,见模块顶部注释。"""
    from lca.infrastructure.tools.run_attachment_scope import get_current_run_attachment_ids

    return get_current_run_attachment_ids()
