"""Ingest package of lca.plugins.transport.webserver.handlers.runs.

Consolidated into deep flat modules per architecture convergence:
- models: data models, constants, settings, and errors
- cache: memory/disk ingest caching
- policy: SSRF and network URL validation policy
- fetcher: HTTP fetching and file integrity validation
- service: message parsing, file reference ingest, and run task preparation
"""

from __future__ import annotations

from lca.plugins.transport.webserver.handlers.runs.ingest.cache import (
    IngestCache,
    IngestCacheEntry,
    cache_key,
    get_ingest_cache,
    reset_ingest_cache_for_tests,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.fetcher import (
    FileFetcher,
    HttpxFileFetcher,
    content_hash,
    decode_data_uri,
    validate_file_integrity,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.models import (
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
from lca.plugins.transport.webserver.handlers.runs.ingest.policy import (
    assert_ingest_url_allowed,
    is_private_or_loopback,
)
from lca.plugins.transport.webserver.handlers.runs.ingest.service import (
    LobeHubRunInput,
    ParsedMessages,
    compose_run_question,
    extract_prior_turns,
    ingest_file_refs,
    load_bytes,
    parse_messages,
    prepare_run_from_messages,
    select_ingest_files,
    try_resolve_local_file,
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
    "LobeHubRunInput",
    "ParsedMessages",
    "assert_ingest_url_allowed",
    "bridge_settings",
    "cache_key",
    "compose_run_question",
    "content_hash",
    "decode_data_uri",
    "extract_prior_turns",
    "get_ingest_cache",
    "ingest_file_refs",
    "is_private_or_loopback",
    "load_bytes",
    "parse_messages",
    "prepare_run_from_messages",
    "reset_ingest_cache_for_tests",
    "select_ingest_files",
    "try_resolve_local_file",
    "validate_file_integrity",
]
