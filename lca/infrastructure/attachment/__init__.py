"""Attachment identity plane — files_info document + run-scoped inbox."""


from collections.abc import Sequence


def _dedupe_ids(attachment_ids: Sequence[str]) -> list[str]:
    """strip → 去空 → 去重（保序）：三处 resolve 的同构前置步骤。

    纯函数，无 store 访问；未知 id 的语义由各调用方自行决定
    （抛 AttachmentError 或显式容忍）。
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw_id in attachment_ids:
        attachment_id = str(raw_id).strip()
        if not attachment_id or attachment_id in seen:
            continue
        seen.add(attachment_id)
        out.append(attachment_id)
    return out

from lca.infrastructure.attachment.layout.layout import AttachmentLayout
from lca.infrastructure.attachment.prompt.prompt import (
    format_machine_uploaded_files_prompt,
    format_sandbox_uploaded_files_prompt,
    resolve_machine_attachment_paths,
    sandbox_attachment_path,
)
from lca.infrastructure.attachment.service.service import FileStoreAttachmentIdentity
from lca.infrastructure.attachment.settings.settings import (
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
