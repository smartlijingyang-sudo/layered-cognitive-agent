"""write_file tool module — file artifact writer."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.tools.builder import build_tools_from_manifest

IDENTIFIER = "write-file"
_MAX_CONTENT_BYTES = 10 * 1024 * 1024
_DEFAULT_MIME = "text/plain"

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="writeFile",
            description=(
                "将文本内容写成可下载文件产物（报告/脚本/HTML 等）。"
                "参数: name（文件名）、content（文本正文）、mime_type（可选 MIME）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "文件名，如 report.md 或 summary.html",
                    },
                    "content": {"type": "string", "description": "要写入的文本内容"},
                    "mime_type": {"type": "string", "description": "可选 MIME，默认 text/plain"},
                },
                "required": ["name", "content"],
            },
        ),
    ),
    meta=ToolMeta(
        avatar="📝",
        title="Write File",
        description="Write text content to a downloadable file artifact",
    ),
)


class WriteFileExecutor:
    def __init__(self, store: FileStore) -> None:
        self._store = store

    def validate(self, api_name: str, args: dict[str, Any]) -> str | None:
        return _validate(args)

    async def writeFile(self, params: dict[str, Any]) -> Observation:  # noqa: N802
        start = time.monotonic()
        error = _validate(params)
        if error:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=error,
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )

        name = str(params["name"]).strip()
        content = str(params["content"])
        mime_type = str(params.get("mime_type") or _DEFAULT_MIME).strip() or _DEFAULT_MIME
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


def _validate(args: dict[str, Any]) -> str | None:
    name = args.get("name")
    content = args.get("content")
    if not isinstance(name, str) or not name.strip():
        return "name 必须是非空文件名"
    if content is None:
        return "content 不能为空"
    if not isinstance(content, str):
        return f"content 必须是字符串，实际类型: {type(content).__name__}"
    if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
        return f"content 超过上限 {_MAX_CONTENT_BYTES} 字节"
    mime = args.get("mime_type")
    if mime is not None and not isinstance(mime, str):
        return "mime_type 必须是字符串"
    return None


def build_tools(store: FileStore) -> list[Tool]:
    return build_tools_from_manifest(MANIFEST, WriteFileExecutor(store))
