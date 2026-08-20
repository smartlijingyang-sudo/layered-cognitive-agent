"""ContextManifest — sole emitter for the journal ``ContextManifested`` event (PR2).

This module is the only place in the codebase allowed to emit
``ContextManifested``.  Other code paths (Reasoner, Brain, runtime_loop)
must consume the manifest, not emit it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.observability.journal import ContextManifested


def digest_manifest(manifest: ContextManifest) -> str:
    """Stable hash of the manifest contents (kind + payload preview).

    The hash is used for replay-side verification: a fresh ``apply_delta``
    fold must produce a manifest with the same digest.
    """
    payload = json.dumps(
        [{"kind": item.kind, "payload": repr(item.payload)} for item in manifest.items],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_manifested_event(
    *,
    step: int,
    items: Sequence[ContextItem],
    persist_full_prompt: bool = False,
) -> tuple[ContextManifested, ContextManifest]:
    """Build the (event, manifest) pair for emission.

    The PerceiveHub is the only caller; the pair is passed to the
    injected ``ManifestSink``. Returns a tuple so the sink can both
    record the manifest content and stay decoupled from the manifest
    builder.
    """
    manifest = ContextManifest(items=tuple(items))
    digest = digest_manifest(manifest)
    event = ContextManifested(
        step=step,
        item_kinds=tuple(item.kind for item in items),
        digest=digest,
        item_refs=(),
        persist_full_prompt=persist_full_prompt,
    )
    return event, manifest


def build_manifest_from_items(items: Sequence[ContextItem]) -> ContextManifest:
    """Pure builder (no emit).  Used by tests and the Hub path."""
    return ContextManifest(items=tuple(items))
