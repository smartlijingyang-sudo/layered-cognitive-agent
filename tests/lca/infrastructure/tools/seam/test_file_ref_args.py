"""Tests for ``lca.infrastructure.tools.seam.file_ref_args`` (ADR-0121 PR-C).

Covers the three shapes the model may emit (``/files/<aid>``, ``http(s)://``,
plain workspace path) plus the ambiguous / unresolved error paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.runtime.attachment_errors import (
    AmbiguousFileRefError,
    UnresolvedFileRefError,
)
from lca.infrastructure.file_store import LocalFileStore
from lca.infrastructure.observability.facade.run_ambit import RunAmbit, bind_run_ambit
from lca.infrastructure.tools.seam.file_ref_args import resolve_path_arg


@pytest.fixture
def store_with_file(tmp_path: Path) -> LocalFileStore:
    s = LocalFileStore(root=tmp_path)
    s.put(data=b"port: 7890\n", name="Clash.yaml", mime_type="text/plain")
    return s


def _first_id(store: LocalFileStore) -> str:
    for k in store._root.iterdir():  # type: ignore[attr-defined]
        return k.name
    raise AssertionError("store empty")


class TestResolvePathArg:
    def test_lca_url_maps_to_filestore_attachment(self, store_with_file: LocalFileStore) -> None:
        aid = _first_id(store_with_file)
        with bind_run_ambit(RunAmbit(file_store=store_with_file)):
            result = resolve_path_arg(f"/files/{aid}")
        assert result.attachment_id == aid
        # Workspace path returned for the host; the dispatch layer wraps with
        # ``resolve_for_plane`` to get the sandbox guest path when needed.
        assert result.file_ref.display_path == "Clash.yaml"
        assert result.file_ref.kind == "user_upload"

    def test_http_url_is_passthrough_with_external_kind(
        self, store_with_file: LocalFileStore
    ) -> None:
        with bind_run_ambit(RunAmbit(file_store=store_with_file)):
            result = resolve_path_arg("https://example.com/x.yaml")
        assert result.file_ref.kind == "user_upload"  # temporary; sandbox curl resolves
        assert result.process_path == "https://example.com/x.yaml"

    def test_absolute_workspace_path_passes_through(self, store_with_file: LocalFileStore) -> None:
        result = resolve_path_arg("/mnt/data/foo.yaml")
        assert result.file_ref.kind == "workspace"
        assert result.process_path == "/mnt/data/foo.yaml"

    def test_relative_path_passes_through(self) -> None:
        result = resolve_path_arg("outputs/x.png")
        assert result.process_path == "outputs/x.png"

    def test_unknown_lca_url_is_unresolved(self, tmp_path: Path) -> None:
        store = LocalFileStore(root=tmp_path)
        with bind_run_ambit(RunAmbit(file_store=store)), pytest.raises(UnresolvedFileRefError):
            resolve_path_arg("/files/file_does_not_exist")

    def test_empty_string_is_unresolved(self, store_with_file: LocalFileStore) -> None:
        with bind_run_ambit(RunAmbit(file_store=store_with_file)), pytest.raises(UnresolvedFileRefError):
            resolve_path_arg("")

    def test_ambiguous_attachment_id_raises(self) -> None:
        aid = "file_collide"
        # Two distinct FileRefs sharing the same attachment_id → ambiguity.
        from lca.contracts.models.core.file_ref import FileRef

        refs = (
            FileRef(
                kind="user_upload",
                target_key=aid,
                display_path="a.yaml",
                process_path="/mnt/data/a.yaml",
                file_url=f"/files/{aid}",
                mime_type="text/plain",
                size_bytes=1,
                source="lobehub_upload",
                attachment_id=aid,
            ),
            FileRef(
                kind="user_upload",
                target_key=aid,
                display_path="b.yaml",
                process_path="/mnt/data/b.yaml",
                file_url=f"/files/{aid}",
                mime_type="text/plain",
                size_bytes=1,
                source="lobehub_upload",
                attachment_id=aid,
            ),
        )
        with pytest.raises(AmbiguousFileRefError):
            resolve_path_arg(f"/files/{aid}", allowed_refs=refs)

    def test_no_filestore_ambient_marks_unresolved(self, store_with_file: LocalFileStore) -> None:
        # No ambient → /files/* cannot resolve.
        aid = _first_id(store_with_file)
        with pytest.raises(UnresolvedFileRefError):
            resolve_path_arg(f"/files/{aid}")
