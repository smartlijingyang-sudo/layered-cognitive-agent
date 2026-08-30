"""Build an Observation from a SandboxResult."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.sandbox import SANDBOX_PREVIEW_CHAR_LIMIT
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.workspace.deliverable import is_office_name

_LOG_MIME = "text/plain"


def _truncate_preview(text: str, limit: int = SANDBOX_PREVIEW_CHAR_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _stored_part(
    store: FileStore, data: bytes, name: str, mime: str, previewable: bool = True
) -> dict[str, Any]:
    """Store a file and return its A2A-aligned metadata dict."""
    s = store.put(data=data, name=name, mime_type=mime)
    return {
        "name": s.name,
        "mimeType": s.mime_type,
        "sizeBytes": s.size_bytes,
        "url": s.url,
        "previewable": previewable,
        "attachmentId": s.attachment_id,
    }


def build_observation(
    store: FileStore, result: Any, invocation_id: str, start: float
) -> Observation:
    """Build an Observation from a SandboxResult, storing generated files."""
    file_parts: list[dict[str, Any]] = []
    for gen in result.generated_files:
        if is_office_name(getattr(gen, "name", "") or ""):
            continue
        file_parts.append(_stored_part(store, gen.data, gen.name, gen.mime_type))
    for label, body in (("stdout", result.stdout), ("stderr", result.stderr)):
        if len(body) > SANDBOX_PREVIEW_CHAR_LIMIT:
            file_parts.append(
                _stored_part(
                    store,
                    body.encode("utf-8", errors="replace"),
                    f"{invocation_id}_{label}.log",
                    _LOG_MIME,
                    previewable=False,
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
