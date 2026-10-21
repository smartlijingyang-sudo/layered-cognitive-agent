import pytest
from pathlib import Path
from lca.infrastructure.file.registry import FileIndexRegistry
from lca.infrastructure.file.store import LocalFileStore
from lca.contracts.models.core.workspace.file_record import VisibilityTier, ReadabilityTier

def test_file_store_writes_directly_to_workspace_user(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = FileIndexRegistry(db_path=tmp_path / "test_files.db")
    store = LocalFileStore(root=workspace, registry=registry)

    # Put a file
    stored = store.put(
        data=b"SELECT * FROM users;",
        name="uuids.sql",
        mime_type="application/sql",
        conversation_id="tpc_12345",
    )

    # 1. Physical file must land in workspace/user/uuids.sql
    user_file = workspace / "user" / "uuids.sql"
    assert user_file.is_file()
    assert user_file.read_bytes() == b"SELECT * FROM users;"

    # 2. Registry must have indexed it
    record = registry.get_by_path("user/uuids.sql")
    assert record is not None
    assert record.file_id == stored.attachment_id
    assert record.path == "user/uuids.sql"
    assert record.visibility == VisibilityTier.INTERNAL
    assert record.readability == ReadabilityTier.NATIVE
    assert record.source_chat_id == "tpc_12345"
    assert record.size_bytes == len(b"SELECT * FROM users;")

    # 3. Read bytes by attachment_id works
    assert store.read_bytes(stored.attachment_id) == b"SELECT * FROM users;"

    # 4. Collision handling: second put with same name appends timestamp/suffix
    stored2 = store.put(
        data=b"SELECT * FROM accounts;",
        name="uuids.sql",
        mime_type="application/sql",
        conversation_id="tpc_12345",
    )
    assert stored2.name != "uuids.sql"
    assert stored2.name.startswith("uuids_")
    assert (workspace / "user" / stored2.name).is_file()

def test_registry_rebuild_from_filesystem(tmp_path: Path):
    workspace = tmp_path / "workspace"
    user_dir = workspace / "user"
    user_dir.mkdir(parents=True)
    your_files = workspace / "your_files"
    your_files.mkdir(parents=True)

    # Create files on disk directly
    (user_dir / "data.csv").write_text("a,b,c\n1,2,3")
    (your_files / "summary.pdf").write_bytes(b"%PDF-1.4 ...")

    db_path = tmp_path / "rebuild_test.db"
    registry = FileIndexRegistry(db_path=db_path)
    count = registry.rebuild_index_from_fs(workspace_root=workspace)
    assert count == 2

    user_rec = registry.get_by_path("user/data.csv")
    assert user_rec is not None
    assert user_rec.visibility == VisibilityTier.INTERNAL
    assert user_rec.readability == ReadabilityTier.NATIVE

    report_rec = registry.get_by_path("your_files/summary.pdf")
    assert report_rec is not None
    assert report_rec.visibility == VisibilityTier.USER
    assert report_rec.readability == ReadabilityTier.CONVERTED


def test_put_origin_owned_by_caller(tmp_path: Path):
    """RA-175: FileRecord.origin 由调用方透传决定，不再是 store 硬编码。

    put(origin="agent_created") 登记 agent_created；默认 put() 仍记 upload
    （向后兼容）。
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = FileIndexRegistry(db_path=tmp_path / "test_origin.db")
    store = LocalFileStore(root=workspace, registry=registry)

    stored_agent = store.put(
        data=b"agent bytes", name="agent.txt", mime_type="text/plain",
        origin="agent_created",
    )
    rec_agent = registry.get_by_path("user/agent.txt")
    assert rec_agent is not None
    assert rec_agent.file_id == stored_agent.attachment_id
    assert rec_agent.origin == "agent_created"

    stored_default = store.put(
        data=b"upload bytes", name="upload.txt", mime_type="text/plain",
    )
    rec_default = registry.get_by_path("user/upload.txt")
    assert rec_default is not None
    assert rec_default.file_id == stored_default.attachment_id
    assert rec_default.origin == "upload"
