"""RA-176: deletion is owned by the FileStore.delete seam.

TrashManager.trash_file delegates path -> attachment id -> store.delete();
the move+sidecar+flag ritual lives in LocalFileStore.delete. Restore and
TTL purge still live on the manager over the .trash/ sidecars.
"""

from pathlib import Path

import pytest

from lca.infrastructure.file.registry import FileIndexRegistry
from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.file.trash import TrashManager


def _seam(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = FileIndexRegistry(db_path=tmp_path / "test.db")
    store = LocalFileStore(root=workspace, registry=registry)
    trash = TrashManager(workspace_root=workspace, registry=registry, store=store)
    return workspace, registry, store, trash


def test_delete_seam_trash_and_restore_cycle(tmp_path: Path):
    """Delete seam owns the ritual; reads go dark via the registry flag."""
    workspace, registry, store, trash = _seam(tmp_path)

    stored = store.put(
        data=b"report bytes v1",
        name="report.pdf",
        mime_type="application/pdf",
        origin="agent_created",
    )
    target = workspace / "user" / "report.pdf"
    assert target.is_file()

    # 1. Delete through the seam (manager delegates path -> id -> seam)
    assert trash.trash_file("user/report.pdf") is True
    assert not target.exists()

    # Registry flags trashed_at; active listing hides it
    rec = registry.get_by_path("user/report.pdf")
    assert rec is not None and rec.trashed_at is not None
    active = registry.list_files(include_trashed=False)
    assert not any(f.path == "user/report.pdf" for f in active)

    # Reads go dark through the interface...
    assert store.get(stored.attachment_id) is None
    assert store.read_bytes(stored.attachment_id) is None
    assert all(s.attachment_id != stored.attachment_id for s in store.list())
    # ...while the {attachment_id}/ mirror blob deliberately survives:
    # the /files/{attachment_id} stable address stays recoverable.
    assert (store.root / stored.attachment_id / "blob").is_file()

    # Trash sidecar written through the shared helper (one meta.json + one blob)
    assert len(list(trash.trash_dir.glob("*.meta.json"))) == 1
    assert len(list(trash.trash_dir.glob("*.blob"))) == 1

    # 2. Restore brings the file back and clears the flag
    assert trash.restore_file("user/report.pdf") is True
    assert target.is_file()
    assert target.read_bytes() == b"report bytes v1"
    rec_after = registry.get_by_path("user/report.pdf")
    assert rec_after is not None and rec_after.trashed_at is None
    assert store.read_bytes(stored.attachment_id) == b"report bytes v1"


def test_delete_unknown_or_rerun_returns_false(tmp_path: Path):
    _, _, store, _ = _seam(tmp_path)
    assert store.delete("file_nope") is False
    stored = store.put(data=b"x", name="x.txt", mime_type="text/plain")
    assert store.delete(stored.attachment_id) is True
    assert store.delete(stored.attachment_id) is False  # already trashed


def test_trash_file_without_store_fails_loud(tmp_path: Path):
    """The standalone ritual is gone; trash_file without a store raises."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = FileIndexRegistry(db_path=tmp_path / "test.db")
    trash = TrashManager(workspace_root=workspace, registry=registry)
    with pytest.raises(RuntimeError):
        trash.trash_file("user/report.pdf")


def test_trash_purge_expired(tmp_path: Path):
    _, _, store, trash = _seam(tmp_path)
    store.put(data=b"old", name="old.txt", mime_type="text/plain")

    assert trash.trash_file("user/old.txt") is True
    assert len(list(trash.trash_dir.glob("*.blob"))) == 1

    # Purge with TTL = 0 (immediately expire everything)
    assert trash.purge_expired(ttl_seconds=-1) == 1
    assert len(list(trash.trash_dir.glob("*.blob"))) == 0
def test_ra179_exists_goes_dark_on_trash(tmp_path: Path):
    """RA-179: exists() must honor trash state like get()/read_bytes()/list().

    Before the fix exists(id) stayed True after delete(id) -- the interface
    disagreed with itself (get(id) is None while exists(id) is True), and
    both production consumers (ingest try_resolve_local_file, sandbox
    runtime_tools.validate) read exists() as validity, so trashed attachments
    passed their checks. Fail-closed: exists() consults _is_trashed first.
    """
    _, _, store, _ = _seam(tmp_path)

    stored = store.put(
        data=b"secret bytes",
        name="secret.txt",
        mime_type="text/plain",
        origin="upload",
    )
    aid = stored.attachment_id
    assert store.exists(aid) is True

    assert store.delete(aid) is True
    assert store.exists(aid) is False

    # The {attachment_id}/ mirror blob deliberately survives for
    # recoverability; only the interface view goes dark.
    assert (store.root / aid / "blob").is_file()
