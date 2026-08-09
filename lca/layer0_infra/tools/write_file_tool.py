"""Generate / write a text file product into the shared FileStore."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, LocalFileStore, get_default_file_store

# Soft cap so a single tool call cannot fill disk (10 MiB text).
_MAX_CONTENT_BYTES = 10 * 1024 * 1024
_DEFAULT_MIME = "text/plain"


class WriteFileTool(Tool):
    """Write text content to a downloadable file artifact.

    Payload is A2A-aligned file metadata (name/mimeType/url/sizeBytes) so
    journal ``ToolInvoked.result_preview`` and the web projector can render
    ``GeneratedFileCard`` without a parallel channel.
    """

    name = "write_file"
    description = (
        "将文本内容写成可下载文件产物（报告/脚本/HTML 等）。"
        "参数: name（文件名）、content（文本正文）、mime_type（可选 MIME）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "文件名，如 report.md 或 summary.html",
            },
            "content": {
                "type": "string",
                "description": "要写入的文本内容",
            },
            "mime_type": {
                "type": "string",
                "description": "可选 MIME，默认 text/plain；HTML 用 text/html",
            },
        },
        "required": ["name", "content"],
    }
    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(self, store: FileStore | LocalFileStore | None = None) -> None:
        self._store: FileStore = store if store is not None else get_default_file_store()

    def validate(self, args: dict[str, Any]) -> str | None:
        name = args.get("name")
        content = args.get("content")
        if not isinstance(name, str) or not name.strip():
            return "name 必须是非空文件名"
        if content is None:
            return "content 不能为空"
        if not isinstance(content, str):
            return f"content 必须是字符串，实际类型: {type(content).__name__}"
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_CONTENT_BYTES:
            return f"content 超过上限 {_MAX_CONTENT_BYTES} 字节"
        mime = args.get("mime_type")
        if mime is not None and not isinstance(mime, str):
            return "mime_type 必须是字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        name = str(args["name"]).strip()
        content = str(args["content"])
        mime_type = str(args.get("mime_type") or _DEFAULT_MIME).strip() or _DEFAULT_MIME
        data = content.encode("utf-8")

        try:
            stored = self._store.put(data=data, name=name, mime_type=mime_type)
        except OSError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"写入文件失败: {exc}",
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        # A2A file-part shape (camelCase keys for frontend GeneratedFile).
        # Never embed full body / previewHtml here — journal result_preview is
        # truncated (~2k); UI loads content via url for preview.
        payload = {
            "name": stored.name,
            "mimeType": stored.mime_type,
            "sizeBytes": stored.size_bytes,
            "url": stored.url,
            "previewable": stored.previewable,
            "attachmentId": stored.attachment_id,
        }
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            latency_ms=latency_ms,
            extra={"files": [payload]},
        )
