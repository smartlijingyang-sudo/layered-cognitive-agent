"""Regression locks for ``LocalFileStore(legacy_root=...)``.

The webserver upload path must store uploaded bytes in the run assistant's
``workspace/user/`` (Workspace SSOT, ADR-0187 / WSOT-08) while keeping the
id-mirror (``/files/{id}`` download surface) on the process-wide store.
``legacy_root`` decouples those two roots; the default keeps the classic
single-root layout byte-for-byte.
"""

from pathlib import Path

from lca.infrastructure.file.store import LocalFileStore


def test_legacy_root_keeps_default_layout_when_omitted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    store = LocalFileStore(root=workspace)

    stored = store.put(data=b"hello", name="a.txt", mime_type="text/plain")

    assert (workspace / "user" / "a.txt").read_bytes() == b"hello"
    assert store.workspace_root == workspace.resolve()
    # Default: mirror lives under {workspace}/uploads/{id}
    assert (workspace / "uploads" / stored.attachment_id / "blob").is_file()
    assert store.read_bytes(stored.attachment_id) == b"hello"


def test_legacy_root_decouples_ownership_from_mirror(tmp_path: Path) -> None:
    owner_workspace = tmp_path / "assistants" / "asst_owner" / "workspace"
    global_mirror = tmp_path / "global" / "uploads"

    store = LocalFileStore(root=owner_workspace / "uploads", legacy_root=global_mirror)

    stored = store.put(
        data=b"csv-bytes",
        name="sales.csv",
        mime_type="text/csv",
        conversation_id="topic_1",
    )

    # Ownership target: the run assistant's workspace/user/.
    assert (owner_workspace / "user" / "sales.csv").read_bytes() == b"csv-bytes"
    # Mirror target: the global store root (download compatibility).
    assert (global_mirror / stored.attachment_id / "blob").read_bytes() == b"csv-bytes"
    # Reads resolve through the mirror, same as the process-wide store.
    assert store.get(stored.attachment_id) is not None
    assert store.read_bytes(stored.attachment_id) == b"csv-bytes"
    assert store.get(stored.attachment_id).conversation_id == "topic_1"  # type: ignore[union-attr]
    assert store.workspace_root == owner_workspace.resolve()
