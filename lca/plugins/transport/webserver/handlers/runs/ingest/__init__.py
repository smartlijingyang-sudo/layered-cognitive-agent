"""ingest subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Re-exports public entry points so callers can
``from lca.plugins.transport.webserver.handlers.runs.ingest import FileFetcher``.
"""

from lca.plugins.transport.webserver.handlers.runs.ingest.cache import (
    IngestCache,
    IngestCacheEntry,
    cache_key,
    get_ingest_cache,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.fetcher import (
    FileFetcher,
    HttpxFileFetcher,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.ingest import FileRef
from lca.plugins.transport.webserver.handlers.runs.ingest.models import FileIntegrityError
from lca.plugins.transport.webserver.handlers.runs.ingest.service import (
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

from lca.plugins.transport.webserver.handlers.runs.ingest.cache import (  # noqa: E402,F401
    reset_ingest_cache_for_tests,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.models import (  # noqa: E402, F401
    FILE_DOWNLOAD_TIMEOUT_S,
    MAX_INGEST_FILE_BYTES,
    MAX_INGEST_FILES,
    FileRef,  # noqa: F811
    IngestResult,
    IngestUrlPolicyError,
    LobeHubBridgeSettings,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.policy import (  # noqa: E402, F401
    assert_ingest_url_allowed,
    is_private_or_loopback,
)
