"""Standing files inspection and editing endpoints for assistant home.

Endpoints:
- GET  /v1/assistants/{assistant_id}/standing-files           -> list_standing_files
- GET  /v1/assistants/{assistant_id}/standing-files/{filename} -> get_standing_file
- PUT  /v1/assistants/{assistant_id}/standing-files/{filename} -> update_standing_file (Task 2)
"""

from __future__ import annotations

import contextlib
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.contracts.protocols.assistant.catalog import ProfilePatch
from lca.plugins.domain.assistant.catalog.plugin import (
    AssistantCatalogError,
)
from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _catalog_from_request,
    _error_envelope,
    _json,
    _not_implemented,
    _ownership_error,
    _ownership_from_request,
    _user_from_request,
)

STANDING_FILES_WHITELIST: tuple[str, ...] = (
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "MEMORY.md",
)


# filename -> ProfilePatch 字段名。SOUL/IDENTITY/USER 三文件经 catalog revise_profile
# 落盘（USER 额外同步 user_store）；MEMORY.md 直接写盘，不进此表。
_PROFILE_PATCH_FIELDS: dict[str, str] = {
    "SOUL.md": "soul_md",
    "IDENTITY.md": "identity_md",
    "USER.md": "user_md",
}


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


def _resolve_assistant_id(request: Request, user_id: str, raw_id: str) -> str:
    """解析助理 ID：优先使用 raw_id，若未匹配且为 agt_* 或 inbox，尝试经由 ownership 映射。"""
    if not raw_id:
        return raw_id
    catalog = _catalog_from_request(request)
    if catalog is not None:
        try:
            catalog.get(raw_id)
            return raw_id
        except (AssistantCatalogError, ValueError):
            pass

    ownership = _ownership_from_request(request)
    if ownership is not None:
        # 1. 尝试以 agent_id 反查 (如 agt_*)
        getter = getattr(ownership, "assistant_id_for_agent", None)
        if getter is not None:
            resolved = getter(raw_id)
            if resolved:
                return resolved

        # 2. 尝试以 client_id (如 lobe-agent:inbox / lobe-agent:{raw_id}) 查
        for candidate_client_id in (f"lobe-agent:{raw_id}", raw_id):
            resolved = ownership.assistant_id_for_client(user_id, candidate_client_id)
            if resolved:
                return resolved

        if raw_id == "inbox":
            resolved = ownership.assistant_id_for_client(user_id, "lobe-agent:inbox")
            if resolved:
                return resolved
            user_assts = ownership.assistant_ids_for(user_id)
            if user_assts:
                return user_assts[0]

    return raw_id


def _prelude(
    request: Request, op: str, filename: str | None = None, verb: str = "accessed"
) -> tuple[str, Any, str] | JSONResponse:
    """三 handler 公共前置：鉴权 → 取 catalog → 解析 assistant_id → 白名单 → ownership。

    成功返回 ``(user_id, catalog, assistant_id)``，失败返回已构造好的错误响应，
    调用方用 ``isinstance(pre, tuple)`` 区分。错误顺序与原三处内联代码一致。
    """
    user_id, auth_error = _user_from_request(request)
    if auth_error is not None:
        return auth_error

    catalog = _catalog_from_request(request)
    if catalog is None:
        return _not_implemented("catalog_unavailable", f"standing_files.{op}")

    raw_id = str(request.path_params.get("assistant_id") or "")
    assistant_id = _resolve_assistant_id(request, user_id, raw_id)

    if filename is not None and filename not in STANDING_FILES_WHITELIST:
        return _error_envelope(
            "disallowed_file",
            status_code=400,
            error_type="invalid_request",
            detail=f"Only standing files {STANDING_FILES_WHITELIST} may be {verb}",
        )

    ownership_error = _ownership_error(request, user_id, assistant_id)
    if ownership_error is not None:
        return ownership_error

    return user_id, catalog, assistant_id


async def list_standing_files(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}/standing-files`` —— 查询 4 大常驻文件元数据与摘要。"""
    pre = _prelude(request, "list")
    if not isinstance(pre, tuple):
        return pre
    _user_id, catalog, assistant_id = pre

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
        size_bytes, line_count = 0, 0
        updated_at, summary = "", ""
        content_hash = sha256_of_str("")
        if file_path.is_file():
            try:
                stat = file_path.stat()
                content = file_path.read_text(encoding="utf-8")
                size_bytes = stat.st_size
                line_count = len(content.splitlines())
                updated_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
                content_hash = sha256_of_str(content)
                summary = _summarize(content)
            except (OSError, UnicodeDecodeError):
                continue
        files_data.append(
            {
                "filename": filename,
                "path": str(file_path),
                "size_bytes": size_bytes,
                "line_count": line_count,
                "updated_at": updated_at,
                "content_hash": content_hash,
                "summary": summary,
            }
        )

    return _json({"assistant_id": assistant_id, "files": files_data}, status_code=200)


async def get_standing_file(request: Request) -> JSONResponse:
    """``GET /v1/assistants/{assistant_id}/standing-files/{filename}`` —— 读取单个常驻文件内容。"""
    filename = str(request.path_params.get("filename") or "")
    pre = _prelude(request, "get", filename=filename, verb="accessed")
    if not isinstance(pre, tuple):
        return pre
    _user_id, catalog, assistant_id = pre

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
    """``PUT /v1/assistants/{assistant_id}/standing-files/{filename}`` —— 更新单个常驻文件内容。"""
    filename = str(request.path_params.get("filename") or "")
    pre = _prelude(request, "update", filename=filename, verb="updated")
    if not isinstance(pre, tuple):
        return pre
    user_id, catalog, assistant_id = pre

    try:
        body = await request.json()
    except (ValueError, OSError):
        return _error_envelope("invalid_json", status_code=400, error_type="invalid_request")
    if not isinstance(body, dict):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="body 必须是 JSON object",
        )

    new_content = body.get("content")
    if not isinstance(new_content, str):
        return _error_envelope(
            "invalid_request",
            status_code=400,
            error_type="invalid_request",
            detail="content 必须为字符串",
        )

    expected_hash = body.get("expected_hash")
    actor = str(body.get("actor") or "user_ui").strip()

    try:
        spec = catalog.get(assistant_id)
    except AssistantCatalogError as exc:
        return _error_envelope(
            "assistant_not_found", status_code=404, error_type="not_found", detail=str(exc)
        )

    home = Path(spec.home_path)
    file_path = home / filename

    # 1. 乐观锁检测：读取当前磁盘真值并核验 hash
    current_content = file_path.read_text(encoding="utf-8") if file_path.is_file() else ""
    current_hash = sha256_of_str(current_content)

    if expected_hash is not None and expected_hash != current_hash:
        return _json(
            {
                "error": {
                    "code": "conflict",
                    "type": "optimistic_lock_conflict",
                    "detail": (
                        f"File {filename} was modified on disk; "
                        f"expected {expected_hash}, got {current_hash}"
                    ),
                    "current_hash": current_hash,
                    "current_content": current_content,
                }
            },
            status_code=409,
        )

    # 2. 执行写盘与同步
    revision_seq = spec.revision_seq
    try:
        patch_field = _PROFILE_PATCH_FIELDS.get(filename)
        if patch_field is not None:
            revision = catalog.revise_profile(
                assistant_id, ProfilePatch(**{patch_field: new_content}), actor=actor
            )
            revision_seq = revision.revision_seq
            if filename == "USER.md":
                # 同步更新 user_store
                user_store = getattr(request.app.state, "user_store", None)
                if user_store is None:
                    user_store = getattr(catalog, "_user_store", None)
                if user_store is not None and user_id:
                    with contextlib.suppress(Exception):
                        user_store.update_user_md(user_id, new_content)
        elif filename == "MEMORY.md":
            # MEMORY.md 不进 catalog profile digest（I-A13），直接原子写盘
            file_path.write_text(new_content, encoding="utf-8")
    except AssistantCatalogError as exc:
        return _error_envelope(
            "invalid_request", status_code=400, error_type="invalid_request", detail=str(exc)
        )

    new_hash = sha256_of_str(new_content)
    stat = file_path.stat()
    mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()

    return _json(
        {
            "assistant_id": assistant_id,
            "filename": filename,
            "path": str(file_path),
            "new_hash": new_hash,
            "revision_seq": revision_seq,
            "updated_at": mtime_iso,
        },
        status_code=200,
    )


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
