"""Attachment identity plane — files_info document + run-scoped inbox."""

from lca.layer0_infra.attachment.layout import AttachmentLayout
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
    "get_attachment_policy",
    "get_attachment_settings",
    "reset_attachment_settings_for_tests",
]
