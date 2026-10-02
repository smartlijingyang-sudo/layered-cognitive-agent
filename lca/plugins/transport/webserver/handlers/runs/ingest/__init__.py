"""ingest subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Re-exports public entry points so callers can
from lca.plugins.transport.webserver.handlers.runs.ingest import FileFetcher.
"""

from lca.plugins.transport.webserver.handlers.runs.ingest.cache.cache import (
    IngestCache,
    IngestCacheEntry,
    cache_key,
    get_ingest_cache,
    reset_ingest_cache_for_tests,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.fetcher.fetcher import (
    FileFetcher,
    HttpxFileFetcher,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.ingest.ingest import FileRef
from lca.plugins.transport.webserver.handlers.runs.ingest.models.models import (
    FILE_DOWNLOAD_TIMEOUT_S,
    MAX_INGEST_FILE_BYTES,
    MAX_INGEST_FILES,
    FileIntegrityError,
    IngestResult,
    IngestUrlPolicyError,
    LobeHubBridgeSettings,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.policy.policy import (
    assert_ingest_url_allowed,
    is_private_or_loopback,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.service.service import (
    ingest_file_refs,
    load_bytes,
    select_ingest_files,
)

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
    "cache_key",
    "get_ingest_cache",
    "ingest_file_refs",
    "is_private_or_loopback",
    "load_bytes",
    "reset_ingest_cache_for_tests",
    "select_ingest_files",
]
