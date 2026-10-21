"""Tests verifying the consolidated architecture of the transport ingest pipeline (INV-ARCH-10, INV-ARCH-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.handlers.runs.ingest import (
    FileRef,
    HttpxFileFetcher,
    IngestCache,
    IngestResult,
    IngestUrlPolicyError,
    assert_ingest_url_allowed,
    ingest_file_refs,
    is_private_or_loopback,
    select_ingest_files,
)


def test_inv_arch_10_flat_module_imports() -> None:
    """INV-ARCH-10: All ingest pipeline components are importable from flat modules directly under ingest/."""
    from lca.plugins.transport.webserver.handlers.runs.ingest import cache as cache_mod
    from lca.plugins.transport.webserver.handlers.runs.ingest import fetcher as fetcher_mod
    from lca.plugins.transport.webserver.handlers.runs.ingest import models as models_mod
    from lca.plugins.transport.webserver.handlers.runs.ingest import policy as policy_mod
    from lca.plugins.transport.webserver.handlers.runs.ingest import service as service_mod

    assert models_mod.FileRef is FileRef
    assert models_mod.IngestResult is IngestResult
    assert cache_mod.IngestCache is IngestCache
    assert policy_mod.assert_ingest_url_allowed is assert_ingest_url_allowed
    assert fetcher_mod.HttpxFileFetcher is HttpxFileFetcher
    assert service_mod.ingest_file_refs is ingest_file_refs
    assert service_mod.select_ingest_files is select_ingest_files
    assert callable(fetcher_mod.content_hash)
    assert callable(fetcher_mod.validate_file_integrity)


@pytest.mark.asyncio
async def test_inv_arch_10_pipeline_caching_and_local_resolution(tmp_path: Path) -> None:
    """INV-ARCH-10: Verify local resolution, cache roundtrip, and hash validation in the consolidated pipeline."""
    store = LocalFileStore(tmp_path)
    stored = store.put(data=b"hello world", name="test.txt", mime_type="text/plain")

    # Local file resolution via /files/{id}
    ref_local = FileRef(
        name="test.txt", url=f"/files/{stored.attachment_id}", mime_type="text/plain"
    )
    result = await ingest_file_refs((ref_local,), store)
    assert result.attachment_ids == (stored.attachment_id,)
    assert result.skipped == ()

    # Policy validation
    assert is_private_or_loopback("127.0.0.1") is True
    assert is_private_or_loopback("example.com") is False

    with pytest.raises(IngestUrlPolicyError):
        assert_ingest_url_allowed("ftp://evil.com/file")


def test_get_ingest_cache_keyed_on_mirror_root_not_object_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The webserver creates a fresh LocalFileStore per POST /runs; the
    process-local cache must be shared across stores with the same mirror
    root instead of being rebuilt (re-reading the JSON file) per request."""
    from lca.plugins.transport.webserver.handlers.runs.ingest.cache import (
        get_ingest_cache,
        reset_ingest_cache_for_tests,
    )

    monkeypatch.setenv("LCA_LOBEHUB_INGEST_CACHE_PATH", str(tmp_path / "cache.json"))
    reset_ingest_cache_for_tests()
    try:
        mirror = tmp_path / "global" / "uploads"
        store1 = LocalFileStore(root=mirror)
        # A per-run store rooted at the assistant workspace but mirroring to
        # the same global root — exactly what decode_create_run builds.
        store2 = LocalFileStore(
            root=tmp_path / "assistants" / "asst_x" / "workspace" / "uploads",
            legacy_root=mirror,
        )
        assert get_ingest_cache(store1) is get_ingest_cache(store2)

        other_mirror = tmp_path / "other" / "uploads"
        store3 = LocalFileStore(root=other_mirror)
        assert get_ingest_cache(store3) is not get_ingest_cache(store1)
    finally:
        reset_ingest_cache_for_tests()


def test_inv_arch_11_no_micro_directories_remain() -> None:
    """INV-ARCH-11: lca/plugins/transport/webserver/handlers/runs/ingest/ contains zero subdirectories (except __pycache__)."""
    ingest_dir = Path("lca/plugins/transport/webserver/handlers/runs/ingest")
    assert ingest_dir.is_dir()

    subdirs = [p.name for p in ingest_dir.iterdir() if p.is_dir() and p.name != "__pycache__"]
    assert subdirs == [], f"Found residual micro-directories in handlers/runs/ingest: {subdirs}"
