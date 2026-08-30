"""ingest subpackage of gateway.runs — split per ADR-0105 §11.2.

Re-exports public entry points so callers can
``from gateway.runs.ingest import FileFetcher``.
"""

from gateway.runs.ingest.cache import (
    IngestCache,
    IngestCacheEntry,
    cache_key,
    get_ingest_cache,
)
from gateway.runs.ingest.fetcher import FileFetcher, HttpxFileFetcher
from gateway.runs.ingest.ingest import FileRef
from gateway.runs.ingest.models import FileIntegrityError
from gateway.runs.ingest.service import (
    ingest_file_refs,
    load_bytes,
    select_ingest_files,
)

__all__ = [
    "FileFetcher",
    "FileIntegrityError",
    "FileRef",
    "HttpxFileFetcher",
    "IngestCache",
    "IngestCacheEntry",
    "cache_key",
    "get_ingest_cache",
    "ingest_file_refs",
    "load_bytes",
    "select_ingest_files",
]
"""
"""

from gateway.runs.ingest.models import (
    FILE_DOWNLOAD_TIMEOUT_S,
    MAX_INGEST_FILES,
    MAX_INGEST_FILE_BYTES,
    FileIntegrityError,
    FileRef,
    IngestResult,
    IngestUrlPolicyError,
    LobeHubBridgeSettings,
)
from gateway.runs.ingest.policy import (
    assert_ingest_url_allowed,
    is_private_or_loopback,
)

from gateway.runs.ingest.cache import (
    IngestCache,
    IngestCacheEntry,
    cache_key,
    get_ingest_cache,
    reset_ingest_cache_for_tests,
)
