from __future__ import annotations

import pytest

from lca.contracts.harness.artifact_manifest import (
    ArtifactEntry,
    ArtifactKind,
    ArtifactManifest,
)


def _entry(artifact_id: str) -> ArtifactEntry:
    return ArtifactEntry(
        artifact_id=artifact_id,
        name="report.md",
        kind=ArtifactKind.REPORT,
        content_hash="sha256:abc",
        media_type="text/markdown",
        uri="artifact://report",
        size_bytes=10,
    )


def test_artifact_manifest_tracks_typed_entries() -> None:
    manifest = ArtifactManifest(task_id="task-1", entries=(_entry("a-1"),))

    assert manifest.entries[0].kind is ArtifactKind.REPORT
    assert manifest.entries[0].content_hash == "sha256:abc"


def test_artifact_manifest_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        ArtifactManifest(task_id="task-1", entries=(_entry("a-1"), _entry("a-1")))


def test_artifact_entry_validates_access_scope() -> None:
    assert _entry("a-2").access_scope == "task"
    with pytest.raises(ValueError, match="access_scope"):
        ArtifactEntry(
            artifact_id="a-3",
            name="secret.txt",
            kind=ArtifactKind.FILE,
            content_hash="sha256:def",
            media_type="text/plain",
            uri="artifact://secret",
            size_bytes=1,
            access_scope="public",
        )
