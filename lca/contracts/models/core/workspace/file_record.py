from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from lca.contracts.models.core.execution.sandbox import SANDBOX_MOUNT_ROOT


class ReadabilityTier(str, Enum):
    NATIVE = "native"
    CONVERTED = "converted"
    VISUAL = "visual"
    OPAQUE = "opaque"


class VisibilityTier(str, Enum):
    USER = "user"
    INTERNAL = "internal"


_NATIVE_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".json",
    ".csv",
    ".yaml",
    ".yml",
    ".ts",
    ".js",
    ".html",
    ".sh",
    ".sql",
    ".xml",
}
_CONVERTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".epub",
    ".rtf",
}
_VISUAL_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def derive_visibility(path: str) -> VisibilityTier:
    clean = str(PurePosixPath(path.lstrip("/"))).replace("\\", "/")
    parts = clean.split("/")
    if parts and parts[0] == "your_files":
        return VisibilityTier.USER
    if len(parts) >= 3 and parts[0] == "goals" and parts[2] == "files":
        return VisibilityTier.USER
    return VisibilityTier.INTERNAL


def classify_readability(filename: str, mime: str = "") -> ReadabilityTier:
    ext = os.path.splitext(filename)[1].lower()
    mime_lower = (mime or "").lower()
    if ext in _NATIVE_EXTENSIONS or mime_lower.startswith("text/") or "sql" in mime_lower:
        return ReadabilityTier.NATIVE
    if (
        ext in _CONVERTED_EXTENSIONS
        or "officedocument" in mime_lower
        or "pdf" in mime_lower
        or "excel" in mime_lower
        or "spreadsheet" in mime_lower
    ):
        return ReadabilityTier.CONVERTED
    if ext in _VISUAL_EXTENSIONS or mime_lower.startswith("image/"):
        return ReadabilityTier.VISUAL
    return ReadabilityTier.OPAQUE


# ---------------------------------------------------------------------------
# Per-audience readability seam (RA-181).
#
# ``classify_readability`` answers the *registry/agent* question: "how will
# this file be read?" (raw text / conversion pipeline / vision / opaque).
# The UI asks a different question: "can the browser inline-render this
# file?" (LobeHub FilePreview coverage). The two audiences genuinely
# diverge -- e.g. a ``.py`` file with unknown mime is NATIVE (agent-readable
# as text) yet the UI has no inline renderer for it, so ui_preview is False.
#
# RA-181 implementer decision: the divergence is *intentional and documented*,
# not a bug to merge away. Convergence happens at rule ownership -- both
# tables live in this one contracts module, so a new extension or mime type
# lands in a single place -- while the two audiences keep their own answers.
# No wire or behavioral change.
# ---------------------------------------------------------------------------

# Mimes the browser can inline-render beyond the tier tables.
_UI_PREVIEW_MIMES = frozenset(
    {
        "application/json",
        "application/javascript",
        "application/xml",
        "application/xhtml+xml",
        "application/pdf",
    }
)

# Extensions the browser can inline-render beyond the tier tables.
_UI_PREVIEW_EXTENSIONS = (
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".json",
    ".xml",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
)

# HTML/XML are never dumped as raw text to the agent -- it reads those via
# browser tools. Owned here so read_text_preview derives from the same tables.
READ_TEXT_PREVIEW_EXCLUDED_MIMES = frozenset(
    {"text/html", "text/xml", "application/xml", "application/xhtml+xml"}
)


@dataclass(frozen=True)
class ReadabilityProfile:
    """One contracts-owned answer to "what can be shown/read of this file".

    ``tier`` answers the registry/agent audience; ``ui_preview`` answers the
    UI audience (inline browser preview). See the RA-181 note above for why
    the two answers are allowed to disagree.
    """

    tier: ReadabilityTier
    ui_preview: bool


def _is_ui_previewable(filename: str, mime: str = "") -> bool:
    """UI may open an in-app preview (iframe / markdown / image), not download-only.

    Aligns with LobeHub FilePreview coverage for common agent products.
    """
    mime_lower = (mime or "").lower().split(";")[0].strip()
    lower = filename.lower()
    if mime_lower.startswith("image/"):
        return True
    if mime_lower.startswith("text/"):
        return True
    if mime_lower in _UI_PREVIEW_MIMES:
        return True
    return lower.endswith(_UI_PREVIEW_EXTENSIONS)


def readability_profile(filename: str, mime: str = "") -> ReadabilityProfile:
    """Classify (filename, mime) once for both audiences.

    The single contracts-owned seam replacing the twin vocabularies
    (infrastructure ``_is_previewable`` + contracts ``classify_readability``).
    """
    return ReadabilityProfile(
        tier=classify_readability(filename, mime),
        ui_preview=_is_ui_previewable(filename, mime),
    )


def to_sandbox_uri(rel_path: str) -> str:
    clean = rel_path.replace(f"{SANDBOX_MOUNT_ROOT}/", "").lstrip("/")
    return f"sandbox://workspace/{clean}"


class FileRecord(BaseModel):
    file_id: str
    path: str
    origin: Literal["upload", "agent_created", "browser_download", "artifact_build"]
    visibility: VisibilityTier
    goal_id: str | None = None
    mime: str = "application/octet-stream"
    size_bytes: int = 0
    readability: ReadabilityTier = ReadabilityTier.OPAQUE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_chat_id: str | None = None
    trashed_at: datetime | None = None


__all__ = [
    "READ_TEXT_PREVIEW_EXCLUDED_MIMES",
    "FileRecord",
    "ReadabilityProfile",
    "ReadabilityTier",
    "VisibilityTier",
    "classify_readability",
    "derive_visibility",
    "readability_profile",
    "to_sandbox_uri",
]
