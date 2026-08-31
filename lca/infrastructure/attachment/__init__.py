"""Attachment identity plane — files_info document + run-scoped inbox."""

from lca.infrastructure.attachment.layout import AttachmentLayout
from lca.infrastructure.attachment.prompt import (
    format_machine_uploaded_files_prompt,
    format_sandbox_uploaded_files_prompt,
    resolve_machine_attachment_paths,
    sandbox_attachment_path,
)
from lca.infrastructure.attachment.service import FileStoreAttachmentIdentity
from lca.infrastructure.attachment.settings import (
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
    "reset_attachment_settings_for_tests",
    "resolve_machine_attachment_paths",
    "sandbox_attachment_path",
]
