"""Regression tests for image ingest MIME handling.

Covers the bug where LobeHub ``imageList`` items (which carry no MIME type)
defaulted to ``image/png`` in ``file_reference_parsing``, so real JPEG uploads
failed the magic-bytes integrity check and were silently dropped. The run
then fell back to the previous user text and re-answered an old question.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.handlers.runs.ingest import (
    FileIntegrityError,
    FileRef,
    load_bytes,
    prepare_run_from_messages,
    validate_file_integrity,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.fetcher import (
    resolve_actual_mime,
    sniff_mime,
)

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00\x01" + b"\x00" * 64
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_sniff_mime_detects_jpeg_and_png_magic_bytes() -> None:
    assert sniff_mime(_JPEG) == "image/jpeg"
    assert sniff_mime(_PNG) == "image/png"
    assert sniff_mime(b"# not a known file") == "application/octet-stream"


def test_resolve_actual_mime_sniffs_content_when_declared_unknown() -> None:
    """LobeHub imageList has no declared MIME; the content's magic bytes win
    even when the HTTP Content-Type is generic ``application/octet-stream``.
    """
    assert resolve_actual_mime(_JPEG, "", "application/octet-stream") == "image/jpeg"
    assert resolve_actual_mime(_PNG, "", "image/png") == "image/png"


def test_resolve_actual_mime_keeps_declared_mime() -> None:
    assert resolve_actual_mime(b"%PDF-1.7", "application/pdf", "application/octet-stream") == (
        "application/pdf"
    )


def test_resolve_actual_mime_does_not_swallow_html_error_pages() -> None:
    """An SPA/error HTML page served for an image URL must remain detectable:
    with no known magic and a text/html HTTP type, the resolved MIME is
    ``application/octet-stream`` so ``validate_file_integrity`` rejects it.
    """
    html = b"<!doctype html><html><body>error</body></html>"
    resolved = resolve_actual_mime(html, "", "text/html")
    assert resolved == "application/octet-stream"
    with pytest.raises(FileIntegrityError):
        validate_file_integrity(html, resolved, "text/html", "page.html")


@pytest.mark.asyncio
async def test_load_bytes_sniffs_jpeg_when_declared_mime_is_empty() -> None:
    class _FakeFetcher:
        async def fetch(self, url: str) -> tuple[bytes, str]:
            return _JPEG, "application/octet-stream"

    ref = FileRef(name="photo.jpg", url="http://10.0.0.1/photo.jpg", mime_type="")
    data, mime = await load_bytes(ref, _FakeFetcher())
    assert data == _JPEG
    assert mime == "image/jpeg"


@pytest.mark.asyncio
async def test_prepare_run_from_messages_ingests_image_only_jpeg(tmp_path: Path) -> None:
    """End-to-end regression: an image-only LobeHub message must ingest the
    JPEG attachment and must NOT reuse the previous user text as the task.
    """
    store = LocalFileStore(tmp_path)

    class _FakeFetcher:
        async def fetch(self, url: str) -> tuple[bytes, str]:
            return _JPEG, "image/jpeg"

    msgs = [
        {"role": "user", "content": "你存在哪里了 文件内容是什么"},
        {"role": "assistant", "content": "查到了"},
        {
            "role": "user",
            "content": "",
            "imageList": [
                {"id": "img-1", "url": "http://10.0.0.1/photo.jpg", "alt": "海量资源每日更.jpg"}
            ],
        },
    ]
    result = await prepare_run_from_messages(
        msgs, store, fetcher=_FakeFetcher(), topic_id="tpc-test"
    )
    assert result.attachment_ids, "JPEG imageList must be ingested, not skipped"
    assert result.user_text, "image-only message must get a task text"
    assert "你存在哪里了" not in result.user_text, "must not reuse previous question"
    assert "海量资源每日更.jpg" in result.question or "photo.jpg" in result.question
