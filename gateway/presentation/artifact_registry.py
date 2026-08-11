"""Artifact registry — centralized URL handling and artifact tracking.

All file artifacts produced by tool invocations are registered here.
The registry ensures:
    1. URLs are always absolute (resolved via LCA_GATEWAY_PUBLIC_URL)
    2. Artifacts are deduplicated by ID
    3. Artifacts are associated with their producing invocation

Design: Registry pattern with URL resolution at registration time.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import urljoin

_log = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────

_DEFAULT_GATEWAY_BASE = "http://127.0.0.1:8765"


def gateway_public_base() -> str:
    """Public HTTP base for ``GET /files/{id}`` (no trailing slash).

    Priority:
        1. LCA_GATEWAY_PUBLIC_URL (explicit override)
        2. OPENAI_PROXY_URL (derived from proxy config)
        3. Default localhost fallback
    """
    raw = (
        os.environ.get("LCA_GATEWAY_PUBLIC_URL", "").strip()
        or os.environ.get("OPENAI_PROXY_URL", "").strip().removesuffix("/v1").rstrip("/")
        or _DEFAULT_GATEWAY_BASE
    )
    return raw.rstrip("/")


def absolutize_url(url: str, *, base: str | None = None) -> str:
    """Convert a relative URL to absolute using the public gateway base."""
    if not url:
        return url
    if url.startswith(("http://", "https://")):
        return url  # Already absolute
    if url.startswith("/"):
        base_url = (base or gateway_public_base()).rstrip("/")
        return urljoin(f"{base_url}/", url.lstrip("/"))
    return url


# ── Artifact value type ─────────────────────────────────────


@dataclass(frozen=True)
class Artifact:
    """First-class product of the run.

    Every file produced by any tool invocation becomes an Artifact.
    URL is *always* absolute (resolved at registration time).
    """

    id: str
    name: str
    mime_type: str
    size_bytes: int
    url: str  # Always absolute
    previewable: bool = False
    produced_by: str = ""  # invocation_id

    def evolve(self, **changes: Any) -> Artifact:
        return replace(self, **changes)


# ── Artifact Registry ───────────────────────────────────────


@dataclass
class ArtifactRegistry:
    """Centralized artifact tracking with URL resolution.

    All file artifacts are registered here. The registry:
        - Resolves relative URLs to absolute
        - Deduplicates by artifact ID
        - Tracks which invocation produced each artifact
    """

    _artifacts: dict[str, Artifact] = field(default_factory=dict)
    _base_url: str | None = None

    def register(
        self,
        *,
        id: str,
        name: str,
        mime_type: str = "",
        size_bytes: int = 0,
        url: str = "",
        previewable: bool = False,
        produced_by: str = "",
    ) -> Artifact:
        """Register a new artifact. URL is resolved to absolute."""
        if not id:
            _log.warning("Artifact registered without ID, skipping: %s", name)
            return None  # type: ignore[return-value]

        # Deduplicate
        if id in self._artifacts:
            return self._artifacts[id]

        # Resolve URL to absolute
        absolute_url = absolutize_url(url, base=self._base_url)

        artifact = Artifact(
            id=id,
            name=name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            url=absolute_url,
            previewable=previewable,
            produced_by=produced_by,
        )
        self._artifacts[id] = artifact
        return artifact

    def register_from_file_part(
        self, file_part: dict[str, Any], *, produced_by: str = ""
    ) -> Artifact | None:
        """Register an artifact from a file part dict (ToolInvoked.files item)."""
        if not isinstance(file_part, dict):
            return None

        name = file_part.get("name", "")
        if not name:
            return None

        id = file_part.get("attachmentId") or file_part.get("attachment_id") or name
        return self.register(
            id=id,
            name=name,
            mime_type=file_part.get("mimeType") or file_part.get("mime_type") or "",
            size_bytes=file_part.get("sizeBytes") or file_part.get("size_bytes") or 0,
            url=file_part.get("url", ""),
            previewable=bool(file_part.get("previewable", False)),
            produced_by=produced_by,
        )

    def register_from_invoked_files(
        self, files: tuple[dict[str, Any], ...], *, produced_by: str = ""
    ) -> list[Artifact]:
        """Register all artifacts from a ToolInvoked event's files."""
        artifacts: list[Artifact] = []
        for file_part in files:
            artifact = self.register_from_file_part(file_part, produced_by=produced_by)
            if artifact is not None:
                artifacts.append(artifact)
        return artifacts

    def get(self, id: str) -> Artifact | None:
        """Get an artifact by ID."""
        return self._artifacts.get(id)

    def list_all(self) -> list[Artifact]:
        """List all registered artifacts in registration order."""
        return list(self._artifacts.values())

    def list_for_invocation(self, invocation_id: str) -> list[Artifact]:
        """List artifacts produced by a specific invocation."""
        return [a for a in self._artifacts.values() if a.produced_by == invocation_id]

    @property
    def count(self) -> int:
        return len(self._artifacts)

    def set_base_url(self, base_url: str) -> None:
        """Set the base URL for resolving relative URLs."""
        self._base_url = base_url

    def clear(self) -> None:
        """Clear all registered artifacts."""
        self._artifacts.clear()


# ── File part utilities ─────────────────────────────────────


def absolutize_file_parts(
    parts: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    *,
    base: str | None = None,
) -> list[dict[str, Any]]:
    """Convert relative URLs in file parts to absolute."""
    result: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        out = dict(part)
        url = out.get("url")
        if isinstance(url, str) and url:
            out["url"] = absolutize_url(url, base=base)
        result.append(out)
    return result
