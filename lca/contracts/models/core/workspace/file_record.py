from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field


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


def to_sandbox_uri(rel_path: str) -> str:
    clean = rel_path.replace("/mnt/data/", "").lstrip("/")
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
    "FileRecord",
    "ReadabilityTier",
    "VisibilityTier",
    "classify_readability",
    "derive_visibility",
    "to_sandbox_uri",
]
