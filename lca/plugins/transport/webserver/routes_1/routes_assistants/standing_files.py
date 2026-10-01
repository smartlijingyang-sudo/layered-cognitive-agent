"""Standing files inspection and editing endpoints for assistant home.

Endpoints:
- GET  /v1/assistants/{assistant_id}/standing-files           -> list_standing_files
- GET  /v1/assistants/{assistant_id}/standing-files/{filename} -> get_standing_file
- PUT  /v1/assistants/{assistant_id}/standing-files/{filename} -> update_standing_file (Task 2)
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.plugins.domain.assistant.catalog.plugin import (
    AssistantCatalogError,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _catalog_from_request,
    _error_envelope,
    _json,
    _not_implemented,
    _ownership_error,
    _user_from_request,
)

STANDING_FILES_WHITELIST: tuple[str, ...] = (
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "MEMORY.md",
)


def sha256_of_str(text: str) -> str:
    """Compute sha256 digest with ``sha256:`` prefix for optimistic concurrency control."""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _summarize(content: str, max_lines: int = 3, max_chars: int = 150) -> str:
    """Extract first lines of markdown as human preview."""
    lines = content.strip().splitlines()
    snippet = "\n".join(lines[:max_lines]).strip()
    if len(snippet) > max_chars:
        return snippet[:max_chars] + "..."
    return snippet


async def list_standing_files(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}/standing-files`` —— 查询 4 大常驻文件元数据与摘要。"""
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error

    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "standing_files.list")

    assistant_id = str(request.path_params.get("assistant_id") or "")
    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    try:
        spec = catalog.get(assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    home = Path(spec.home_path)
    files_data: list[dict[str, Any]] = []

    for filename in STANDING_FILES_WHITELIST:
        file_path = home / filename
        if file_path.is_file():
            try:
                stat = file_path.stat()
                content = file_path.read_text(encoding="utf-8")
                mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
                files_data.append(
                    {
                        "filename": filename,
                        "path": str(file_path),
                        "size_bytes": stat.st_size,
                        "line_count": len(content.splitlines()),
                        "updated_at": mtime_iso,
                        "content_hash": sha256_of_str(content),
                        "summary": _summarize(content),
                    }
                )
            except (OSError, UnicodeDecodeError):
                continue
        else:
            files_data.append(
                {
                    "filename": filename,
                    "path": str(file_path),
                    "size_bytes": 0,
                    "line_count": 0,
                    "updated_at": "",
                    "content_hash": sha256_of_str(""),
                    "summary": "",
                }
            )

    return _json({"assistant_id": assistant_id, "files": files_data}, status_code=200)


async def get_standing_file(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}/standing-files/{filename}`` —— 读取单个常驻文件内容。"""
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error

    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", "standing_files.get")

    assistant_id = str(request.path_params.get("assistant_id") or "")
    filename = str(request.path_params.get("filename") or "")

    if filename not in STANDING_FILES_WHITELIST:
        return _error_envelope(
            "disallowed_file",
            status_code=400,
            error_type="invalid_request",
            detail=f"Only standing files {STANDING_FILES_WHITELIST} may be accessed",
        )

    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    try:
        spec = catalog.get(assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    file_path = Path(spec.home_path) / filename
    if not file_path.is_file():
        return _error_envelope(
            "file_not_found",
            status_code=404,
            error_type="not_found",
            detail=f"Standing file {filename} does not exist",
        )

    try:
        stat = file_path.stat()
        content = file_path.read_text(encoding="utf-8")
        mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    except OSError as exc:
        return _error_envelope(
            "file_read_error", status_code=500, error_type="internal", detail=str(exc)
        )

    return _json(
        {
            "assistant_id": assistant_id,
            "filename": filename,
            "path": str(file_path),
            "content": content,
            "content_hash": sha256_of_str(content),
            "updated_at": mtime_iso,
        },
        status_code=200,
    )


async def update_standing_file(request: Request) -> JSONResponse:
    """``PUT /v1/assistants/{assistant_id}/standing-files/{filename}`` (Task 2 Placeholder)."""
    return _not_implemented("update_standing_file_not_implemented")


async def standing_file_dispatcher(request: Request) -> JSONResponse:
    """``/v1/assistants/{assistant_id}/standing-files/{filename}`` method dispatcher."""
    method = str(getattr(request, "method", "")).upper()
    if method == "GET":
        return await get_standing_file(request)
    if method == "PUT":
        return await update_standing_file(request)
    if method == "OPTIONS":
        return _json({}, status_code=200)
    return _error_envelope(
        "method_not_allowed", status_code=405, detail=f"Unsupported method {method}"
    )
