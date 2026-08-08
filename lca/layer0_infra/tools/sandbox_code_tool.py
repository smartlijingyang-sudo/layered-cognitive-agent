"""Run code in an isolated sandbox; stream deltas via journal; store file products."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_PREVIEW_CHAR_LIMIT,
)
from lca.contracts.protocols import Sandbox, Tool
from lca.layer0_infra.file_store import FileStore, LocalFileStore, get_default_file_store

SANDBOX_TOOL_NAME = "run_sandbox_code"

_LOG_MIME = "text/plain"


def _truncate_preview(text: str, limit: int = SANDBOX_PREVIEW_CHAR_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _file_part(
    *,
    name: str,
    mime_type: str,
    size_bytes: int,
    url: str,
    previewable: bool,
    attachment_id: str,
) -> dict[str, Any]:
    """A2A-aligned file metadata (camelCase) for frontend GeneratedFile cards."""
    return {
        "name": name,
        "mimeType": mime_type,
        "sizeBytes": size_bytes,
        "url": url,
        "previewable": previewable,
        "attachmentId": attachment_id,
    }


class SandboxCodeTool(Tool):
    """Execute code in a Sandbox; optional attachment mounts; multi-file products."""

    name = SANDBOX_TOOL_NAME
    description = (
        "在隔离沙箱中执行代码（默认 Python），可选挂载已上传附件到 /mnt/data，"
        "返回 stdout/stderr 与生成文件产物。"
        "参数: code（必填）、language（可选，默认 python）、"
        "attachment_ids（可选，FileStore 中的附件 id 列表）、"
        "timeout_s（可选，秒）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要在沙箱中执行的源代码",
            },
            "language": {
                "type": "string",
                "description": "语言，MVP 仅 python",
                "default": "python",
            },
            "attachment_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要挂载进沙箱 /mnt/data 的附件 id 列表",
            },
            "timeout_s": {
                "type": "integer",
                "description": f"执行超时秒数，默认 {DEFAULT_SANDBOX_TIMEOUT_S}",
            },
        },
        "required": ["code"],
    }
    is_idempotent = False
    default_timeout_s = DEFAULT_SANDBOX_TIMEOUT_S

    def __init__(
        self,
        sandbox: Sandbox,
        store: FileStore | LocalFileStore | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._store: FileStore = store if store is not None else get_default_file_store()

    def validate(self, args: dict[str, Any]) -> str | None:
        code = args.get("code")
        if not isinstance(code, str) or not code.strip():
            return "code 必须是非空字符串"
        language = args.get("language", "python")
        if language is not None and not isinstance(language, str):
            return "language 必须是字符串"
        attachment_ids = args.get("attachment_ids")
        if attachment_ids is not None:
            if not isinstance(attachment_ids, list):
                return "attachment_ids 必须是字符串列表"
            for item in attachment_ids:
                if not isinstance(item, str) or not item.strip():
                    return "attachment_ids 各项必须是非空字符串"
                if not self._store.exists(item.strip()):
                    return f"附件不存在: {item}"
        timeout_s = args.get("timeout_s")
        if timeout_s is not None and not isinstance(timeout_s, (int, float)):
            return "timeout_s 必须是数字"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        code = str(args["code"])
        language = str(args.get("language") or "python").strip() or "python"
        raw_ids = args.get("attachment_ids") or []
        attachment_ids = [str(i).strip() for i in raw_ids if str(i).strip()]
        timeout_raw = args.get("timeout_s", DEFAULT_SANDBOX_TIMEOUT_S)
        try:
            timeout_s = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_s = DEFAULT_SANDBOX_TIMEOUT_S

        mount_files: dict[str, bytes] = {}
        for aid in attachment_ids:
            meta = self._store.get(aid)
            data = self._store.read_bytes(aid)
            if meta is None or data is None:
                latency_ms = int((time.monotonic() - start) * 1000)
                return Observation(
                    observation_id=new_id("obs"),
                    success=False,
                    payload=None,
                    error=f"附件不存在或不可读: {aid}",
                    latency_ms=latency_ms,
                    extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
                )
            mount_files[meta.name] = data

        invocation_id = new_id("sbx")
        result = await self._sandbox.run(
            code=code,
            language=language,
            files=mount_files or None,
            timeout_s=timeout_s,
            invocation_id=invocation_id,
        )

        file_parts: list[dict[str, Any]] = []
        for gen in result.generated_files:
            stored = self._store.put(
                data=gen.data,
                name=gen.name,
                mime_type=gen.mime_type,
            )
            file_parts.append(
                _file_part(
                    name=stored.name,
                    mime_type=stored.mime_type,
                    size_bytes=stored.size_bytes,
                    url=stored.url,
                    previewable=stored.previewable,
                    attachment_id=stored.attachment_id,
                )
            )

        # Oversized logs become downloadable .log products (ADR-0044).
        for label, body in (("stdout", result.stdout), ("stderr", result.stderr)):
            if len(body) > SANDBOX_PREVIEW_CHAR_LIMIT:
                stored = self._store.put(
                    data=body.encode("utf-8"),
                    name=f"{invocation_id}_{label}.log",
                    mime_type=_LOG_MIME,
                )
                file_parts.append(
                    _file_part(
                        name=stored.name,
                        mime_type=stored.mime_type,
                        size_bytes=stored.size_bytes,
                        url=stored.url,
                        previewable=False,
                        attachment_id=stored.attachment_id,
                    )
                )

        latency_ms = int((time.monotonic() - start) * 1000)
        payload: dict[str, Any] = {
            "stdout": _truncate_preview(result.stdout),
            "stderr": _truncate_preview(result.stderr),
            "files": file_parts,
            "exit_code": result.exit_code,
            "invocation_id": invocation_id,
        }
        if not result.success:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=payload,
                content_type=ContentType.STRUCTURED,
                error=result.error or "sandbox execution failed",
                latency_ms=latency_ms,
                extra={
                    "invocation_id": invocation_id,
                    "files": file_parts,
                    FAILURE_KIND: FAILURE_KIND_EXECUTION,
                },
            )

        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            latency_ms=latency_ms,
            extra={"invocation_id": invocation_id, "files": file_parts},
        )
