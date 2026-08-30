"""GET /files/{id} and meta. No Run lifecycle."""

from __future__ import annotations

from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gateway.cors import CORS_HEADERS
from lca.infrastructure.file_store import LocalFileStore


def content_disposition(disposition_type: str, filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    encoded = quote(filename, safe="")
    return f"{disposition_type}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


async def download_file(request: Request, store: LocalFileStore) -> Response:
    attachment_id = request.path_params["attachment_id"]
    meta = store.get(attachment_id)
    data = store.read_bytes(attachment_id)
    if meta is None or data is None:
        return JSONResponse({"error": "file not found"}, status_code=404, headers=CORS_HEADERS)

    want_inline = request.query_params.get("preview") == "1" or meta.mime_type.lower().startswith(
        "image/"
    )
    if want_inline and (meta.previewable or meta.mime_type.lower().startswith("image/")):
        return Response(
            content=data,
            media_type=meta.mime_type,
            headers={
                **CORS_HEADERS,
                "Content-Disposition": content_disposition("inline", meta.name),
                "Content-Length": str(len(data)),
                "Cache-Control": "private, max-age=3600",
            },
        )

    return Response(
        content=data,
        media_type=meta.mime_type,
        headers={
            **CORS_HEADERS,
            "Content-Disposition": content_disposition("attachment", meta.name),
            "Content-Length": str(len(data)),
        },
    )


async def get_file_meta(request: Request, store: LocalFileStore) -> JSONResponse:
    attachment_id = request.path_params["attachment_id"]
    meta = store.get(attachment_id)
    if meta is None:
        return JSONResponse({"error": "file not found"}, status_code=404, headers=CORS_HEADERS)
    return JSONResponse(
        {
            "attachment_id": meta.attachment_id,
            "name": meta.name,
            "mime_type": meta.mime_type,
            "url": meta.url,
            "size_bytes": meta.size_bytes,
            "previewable": meta.previewable,
        },
        headers=CORS_HEADERS,
    )
