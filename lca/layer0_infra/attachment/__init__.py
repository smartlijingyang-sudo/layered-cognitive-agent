"""Attachment identity plane — files_info document + run-scoped inbox."""

from lca.layer0_infra.attachment.layout import AttachmentLayout
from lca.layer0_infra.attachment.prompt import (
    format_machine_uploaded_files_prompt,
    format_sandbox_uploaded_files_prompt,
    render_dsh_workspace_context,
    resolve_machine_attachment_paths,
    sandbox_attachment_path,
)
from lca.layer0_infra.attachment.service import FileStoreAttachmentIdentity
from lca.layer0_infra.attachment.settings import (
    AttachmentPolicyDocument,
    AttachmentSettings,
    get_attachment_policy,
    get_attachment_settings,
    reset_attachment_settings_for_tests,
)

__all__ = [
    "AttachmentLayout",
    "AttachmentPolicyDocument",
    "AttachmentSettings",
    "FileStoreAttachmentIdentity",
    "format_machine_uploaded_files_prompt",
    "format_sandbox_uploaded_files_prompt",
    "get_attachment_policy",
    "get_attachment_settings",
    "render_dsh_workspace_context",
    "reset_attachment_settings_for_tests",
    "resolve_machine_attachment_paths",
    "sandbox_attachment_path",
]
