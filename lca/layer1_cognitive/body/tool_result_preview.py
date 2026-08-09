"""工具结果预览压缩 —— SafeExecutor journal 用，避免大 payload 撑爆预览。"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.decision import Observation

# Keep journal result_preview well under AttributePolicy generic 2k cap while
# remaining useful for console/LLM memory; structured files go on ToolInvoked.files.
_RESULT_PREVIEW_STREAM_CHARS = 400
_STRIP_FROM_PREVIEW = frozenset({"previewHtml", "preview_html", "content"})
_FILE_META_KEYS = (
    "name",
    "mimeType",
    "mime_type",
    "sizeBytes",
    "size_bytes",
    "url",
    "previewable",
    "attachmentId",
    "attachment_id",
)


def thin_file_part(part: dict[str, Any]) -> dict[str, Any]:
    """Metadata-only file part (no body / previewHtml)."""
    out: dict[str, Any] = {}
    for key in _FILE_META_KEYS:
        if key in part and part[key] is not None:
            out[key] = part[key]
    return out


def tool_files(obs: Observation) -> tuple[dict[str, Any], ...]:
    """Extract A2A file parts for ToolInvoked.files (never truncated by policy)."""
    extra = obs.extra or {}
    raw = extra.get("files")
    if isinstance(raw, list) and raw:
        return tuple(thin_file_part(f) for f in raw if isinstance(f, dict) and f.get("name"))

    payload = obs.payload
    if not isinstance(payload, dict):
        return ()
    nested = payload.get("files")
    if isinstance(nested, list) and nested:
        return tuple(thin_file_part(f) for f in nested if isinstance(f, dict) and f.get("name"))

    # Single-file tools (write_file): payload is the file part itself.
    if payload.get("name") and (payload.get("mimeType") or payload.get("mime_type")):
        return (thin_file_part(payload),)
    return ()


def compact_payload_for_preview(payload: Any) -> Any:
    """Drop heavy fields so result_preview survives 2k truncation as valid-ish summary."""
    if not isinstance(payload, dict):
        return payload
    compact: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _STRIP_FROM_PREVIEW:
            continue
        if key in {"stdout", "stderr"} and isinstance(value, str):
            if len(value) > _RESULT_PREVIEW_STREAM_CHARS:
                compact[key] = value[:_RESULT_PREVIEW_STREAM_CHARS] + "..."
            else:
                compact[key] = value
            continue
        if key == "files" and isinstance(value, list):
            compact[key] = [
                thin_file_part(f) for f in value if isinstance(f, dict) and f.get("name")
            ]
            continue
        if isinstance(value, str) and len(value) > _RESULT_PREVIEW_STREAM_CHARS:
            compact[key] = value[:_RESULT_PREVIEW_STREAM_CHARS] + "..."
            continue
        compact[key] = value
    return compact
