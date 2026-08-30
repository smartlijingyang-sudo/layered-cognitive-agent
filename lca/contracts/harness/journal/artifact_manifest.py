"""Durable manifest for artifacts emitted by an Agent run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArtifactKind(StrEnum):
    FILE = "file"
    REPORT = "report"
    IMAGE = "image"
    DATASET = "dataset"


@dataclass(frozen=True)
class ArtifactEntry:
    artifact_id: str
    name: str
    kind: ArtifactKind
    content_hash: str
    media_type: str
    uri: str
    size_bytes: int
    owner: str = ""
    access_scope: str = "task"

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.artifact_id, self.name, self.content_hash, self.media_type, self.uri)
        ):
            raise ValueError("artifact identity fields must not be empty")
        if self.size_bytes < 0:
            raise ValueError("artifact size must be non-negative")
        if self.access_scope not in {"task", "session", "private"}:
            raise ValueError("artifact access_scope is invalid")


@dataclass(frozen=True)
class ArtifactManifest:
    task_id: str
    entries: tuple[ArtifactEntry, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("artifact manifest task_id must not be empty")
        if self.version <= 0:
            raise ValueError("artifact manifest version must be positive")
        ids = [entry.artifact_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("artifact IDs must be unique within a manifest")


__all__ = ["ArtifactEntry", "ArtifactKind", "ArtifactManifest"]
