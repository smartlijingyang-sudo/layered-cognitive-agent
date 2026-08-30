"""工具结果文件元数据 —— ToolInvoked.files 一等字段。

职责边界：
- ``thin_file_part`` / ``tool_files`` → 文件元数据一等字段（metadata-only，不截断）

ADR-0101 PR-3:journal 的 ToolStarted/ToolInvoked 不再携带
``arguments_preview`` / ``result_preview`` / ``plugin_state`` 等 view-only
字段；参数和结果经 ``arguments_ref`` / ``output_ref`` 走 evidence 平面。
LobeHub UI 渲染由 renderer registry（PR-4）按 ``tool_name`` 派发,本模块
不再持有 UI 塑形职责。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.decision import Observation

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

__all__ = [
    "thin_file_part",
    "tool_files",
]


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
