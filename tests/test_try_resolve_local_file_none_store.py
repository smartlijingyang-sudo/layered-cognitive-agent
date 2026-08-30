"""Regression: ``try_resolve_local_file`` must not crash when ``store is None``.

Before the fix, gateway boot paths that did not wire a bootstrap_factory
(``scripts/serve_observability.py``) left ``app.state.file_store is None``,
so any incoming POST /runs carrying a ``fileList`` / ``imageList`` (or the
LcaRunDriver's ``files`` field) hit::

    AttributeError: 'NoneType' object has no attribute 'exists'

inside ``ingest_file_refs`` → ``try_resolve_local_file`` and returned HTTP
500. The contract is now: a missing store means "skip local resolution;
let the remote/cache fallback try to attach" — same as ``None`` would
have meant downstream.

Two related fixes (same commit) close the regression at both layers:

1. ``gateway/app.py`` now defaults ``app = create_app(file_store=LocalFileStore(...))``
   at module load, so the script-launched gateway always has a real store.
2. ``gateway/runs/ingest_service.py::try_resolve_local_file`` is defensive
   against ``store=None`` so a future caller that drops the store can't
   500 the request.

This test exercises only (2) — the helper function directly — so it stays
independent of the boot wiring.
"""

from __future__ import annotations

from gateway.runs.ingest import FileRef
from gateway.runs.ingest.service import try_resolve_local_file


def _make_ref(*, url: str, lobehub_id: str = "") -> FileRef:
    return FileRef(
        name="hello.txt",
        url=url,
        mime_type="text/plain",
        lobehub_id=lobehub_id,
        size_bytes=12,
        source="files",
    )


def test_try_resolve_local_file_returns_none_when_store_is_none() -> None:
    """Absolute URL + non-empty lobehub_id + None store → no crash, returns None."""
    ref = _make_ref(
        url="http://10.36.6.252:3010/files/file_abc",
        lobehub_id="file_abc",
    )
    # Must not raise AttributeError.
    assert try_resolve_local_file(ref, None) is None


def test_try_resolve_local_file_local_url_with_none_store() -> None:
    """Local ``/files/{id}`` URL + None store → no crash, returns None."""
    ref = _make_ref(url="/files/file_abc", lobehub_id="")
    assert try_resolve_local_file(ref, None) is None


def test_try_resolve_local_file_empty_lobehub_id_with_none_store() -> None:
    """Absolute URL + empty lobehub_id + None store → no crash, returns None."""
    ref = _make_ref(
        url="http://10.36.6.252:3010/files/file_abc",
        lobehub_id="",
    )
    assert try_resolve_local_file(ref, None) is None
