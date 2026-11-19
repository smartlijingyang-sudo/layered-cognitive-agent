"""``POST /files`` — accept browser uploads, archive them, hand back attachments.

Eager semantics: the bytes are validated and written to the ``FileStore`` during
the request, so the run path never touches the external file service again and
the one-hour authorized link never becomes runtime state.

All-or-nothing: any failure leaves no partial local file behind.
"""

from __future__ import annotations

import logging
import mimetypes

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse

from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS
from lca.plugins.transport.webserver.handlers.files.fileservice import (
    FileServiceClient,
    FileServiceContractViolationError,
    FileServiceError,
    FileServiceUnavailableError,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.fetcher import (
    sniff_mime,
    validate_file_integrity,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.models import (
    MAX_INGEST_FILE_BYTES,
    MAX_INGEST_FILES,
    FileIntegrityError,
)

_log = logging.getLogger(__name__)

_UPLOAD_FIELD = "files"
_GENERIC_MIME = "application/octet-stream"


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": message, "type": "invalid_request_error", "code": code}},
        status_code=status_code,
        headers=CORS_HEADERS,
    )


def _resolve_mime(declared: str, actual: str) -> str:
    """Prefer the wire-declared MIME, fall back to magic bytes."""
    if declared and declared != _GENERIC_MIME:
        return declared
    return actual or _GENERIC_MIME


async def _collect_uploads(
    request: Request,
) -> tuple[list[tuple[str, bytes, str]], JSONResponse | None]:
    """Parse and validate the multipart body. Returns ``(files, failure)``."""
    form = await request.form()
    uploads = [item for item in form.getlist(_UPLOAD_FIELD) if isinstance(item, UploadFile)]
    if not uploads:
        return [], _error(400, "missing_files", f"multipart field {_UPLOAD_FIELD!r} is required")
    if len(uploads) > MAX_INGEST_FILES:
        return [], _error(400, "too_many_files", f"at most {MAX_INGEST_FILES} files per request")
    collected: list[tuple[str, bytes, str]] = []
    for upload in uploads:
        name = (upload.filename or "").strip() or "file"
        data = await upload.read()
        if len(data) > MAX_INGEST_FILE_BYTES:
            return [], _error(
                400, "file_too_large", f"{name} exceeds {MAX_INGEST_FILE_BYTES} bytes"
            )
        declared = (upload.content_type or "").strip()
        actual = sniff_mime(data)
        try:
            validate_file_integrity(data, declared, actual, name)
        except FileIntegrityError as exc:
            return [], _error(400, "invalid_file", str(exc))
        guessed = mimetypes.guess_type(name)[0] or ""
        collected.append((name, data, _resolve_mime(declared or guessed, actual)))
    return collected, None


async def upload_files(request: Request, client: FileServiceClient | None) -> JSONResponse:
    """Archive uploaded bytes locally and mirror them to the company file service."""
    store = getattr(request.app.state, "file_store", None)
    if store is None:
        return _error(503, "file_store_unavailable", "file store is not mounted")
    if client is None:
        return _error(
            503,
            "fileservice_unconfigured",
            "company file service credentials are not configured",
        )

    files, failure = await _collect_uploads(request)
    if failure is not None:
        return failure

    try:
        sources = await client.upload_sources(files)
    except FileServiceUnavailableError as exc:
        return _error(502, "fileservice_unavailable", str(exc))
    except FileServiceContractViolationError as exc:
        return _error(502, "fileservice_contract_violation", str(exc))
    except FileServiceError as exc:
        return _error(502, "fileservice_error", str(exc))

    stored_files: list[dict[str, object]] = []
    for (name, data, mime), source in zip(files, sources, strict=True):
        stored = store.put(
            data=data,
            name=name,
            mime_type=mime,
            origin="upload",
            source_url=source,
        )
        stored_files.append(
            {
                "attachment_id": stored.attachment_id,
                "url": stored.url,
                "name": stored.name,
                "size_bytes": stored.size_bytes,
                "mime_type": stored.mime_type,
                "source": stored.source_url,
            }
        )
    _log.info("fileservice.files_uploaded count=%d", len(stored_files))
    return JSONResponse({"files": stored_files}, headers=CORS_HEADERS)
