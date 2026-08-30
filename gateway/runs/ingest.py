"""Compatibility facade for the governed LobeHub-to-FileStore ingest pipeline.

The ingest boundary has four independent concerns: typed policy/configuration,
remote URL authorization, byte integrity, and cache-backed mirroring.  Their
implementations live in focused sibling modules; this facade preserves the
established Gateway import path for callers and tests.
"""

from __future__ import annotations

from gateway.runs.ingest_cache import (
    IngestCache,
    IngestCacheEntry,
    get_ingest_cache,
    reset_ingest_cache_for_tests,
)
from gateway.runs.ingest_fetcher import FileFetcher, HttpxFileFetcher
from gateway.runs.ingest_integrity import content_hash, validate_file_integrity
from gateway.runs.ingest_models import (
    FILE_DOWNLOAD_TIMEOUT_S,
    MAX_INGEST_FILE_BYTES,
    MAX_INGEST_FILES,
    FileIntegrityError,
    FileRef,
    IngestResult,
    IngestUrlPolicyError,
    LobeHubBridgeSettings,
    bridge_settings,
)
from gateway.runs.ingest_policy import assert_ingest_url_allowed
from gateway.runs.ingest_service import ingest_file_refs, select_ingest_files

__all__ = [
    "FILE_DOWNLOAD_TIMEOUT_S",
    "MAX_INGEST_FILES",
    "MAX_INGEST_FILE_BYTES",
    "FileFetcher",
    "FileIntegrityError",
    "FileRef",
    "HttpxFileFetcher",
    "IngestCache",
    "IngestCacheEntry",
    "IngestResult",
    "IngestUrlPolicyError",
    "LobeHubBridgeSettings",
    "assert_ingest_url_allowed",
    "bridge_settings",
    "content_hash",
    "get_ingest_cache",
    "ingest_file_refs",
    "reset_ingest_cache_for_tests",
    "select_ingest_files",
    "validate_file_integrity",
]
