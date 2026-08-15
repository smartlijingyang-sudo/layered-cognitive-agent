"""LobeHub-compatible <files_info> document (pydantic, type-safe render).

Content normalization: user-uploaded text is normalized (Unicode quotes,
dashes, zero-width chars → ASCII equivalents) *before* injection so that
downstream code generation never receives syntax-breaking characters.
Original bytes in FileStore are never mutated.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.models.core.attachment import AttachmentRecord
from lca.layer0_infra.attachment.normalizer import normalize_for_injection
from lca.layer0_infra.attachment.settings import AttachmentPolicyDocument, get_attachment_policy


class FilesInfoFile(BaseModel):
    """One <file> node. Field names match LobeHub wire attributes."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    type: str
    size: int = Field(ge=0)
    url: str = ""
    content: str = ""

    @classmethod
    def from_record(cls, record: AttachmentRecord) -> FilesInfoFile:
        return cls(
            id=record.attachment_id,
            name=record.name,
            type=record.mime_type,
            size=max(record.size_bytes, 0),
            url=record.url,
            content=normalize_for_injection(record.content or ""),
        )

    def to_xml(self) -> str:
        attrs = (
            f'id="{html.escape(self.id, quote=True)}" '
            f'name="{html.escape(self.name, quote=True)}" '
            f'type="{html.escape(self.type, quote=True)}" '
            f'size="{self.size}"'
        )
        if self.url:
            attrs = f'{attrs} url="{html.escape(self.url, quote=True)}"'
        if self.content:
            return f"<file {attrs}>{html.escape(self.content)}</file>"
        return f"<file {attrs}></file>"


class FilesInfoDocument(BaseModel):
    """The SYSTEM CONTEXT block injected into the current user turn."""

    model_config = ConfigDict(frozen=True)

    instruction: str
    files: tuple[FilesInfoFile, ...]
    open_marker: str
    close_marker: str

    @classmethod
    def from_records(
        cls,
        records: Sequence[AttachmentRecord],
        *,
        policy: AttachmentPolicyDocument | None = None,
    ) -> FilesInfoDocument:
        doc_policy = policy if policy is not None else get_attachment_policy()
        return cls(
            instruction=doc_policy.files_instruction.strip(),
            files=tuple(FilesInfoFile.from_record(record) for record in records),
            open_marker=doc_policy.system_context_open,
            close_marker=doc_policy.system_context_close,
        )

    def render(self) -> str:
        if not self.files:
            return ""
        body = "\n".join(item.to_xml() for item in self.files)
        return (
            f"{self.open_marker}\n"
            f"<context.instruction>{html.escape(self.instruction)}</context.instruction>\n"
            f"<files_info>\n"
            f"<files>\n"
            f"<files_docstring>here are user upload files you can refer to</files_docstring>\n"
            f"{body}\n"
            f"</files>\n"
            f"</files_info>\n"
            f"{self.close_marker}"
        )
