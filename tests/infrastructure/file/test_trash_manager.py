import pytest
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from lca.infrastructure.file.registry import FileIndexRegistry
from lca.infrastructure.file.trash import TrashManager
from lca.contracts.models.core.workspace.file_record import FileRecord, VisibilityTier, ReadabilityTier

def test_trash_and_restore_cycle(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "your_files" / "report.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"report bytes v1")
    
    registry = FileIndexRegistry(db_path=tmp_path / "test.db")
    # Register the file
    registry.register(
        FileRecord(
            file_id="f_rep1",
            path="your_files/report.pdf",
            origin="agent_created",
            visibility=VisibilityTier.USER,
            size_bytes=len(b"report bytes v1"),
            readability=ReadabilityTier.CONVERTED,
        )
    )
    
    trash = TrashManager(workspace_root=workspace, registry=registry)
    
    # 1. Trash the file
    res = trash.trash_file("your_files/report.pdf")
    assert res is True
    assert not target.exists()
    
    # File in registry must have trashed_at set
    rec = registry.get_by_path("your_files/report.pdf")
    assert rec is not None
    assert rec.trashed_at is not None
    # Must not show up in active listing
    active_files = registry.list_files(include_trashed=False)
    assert not any(f.path == "your_files/report.pdf" for f in active_files)
    
    # 2. Restore the file
    restored = trash.restore_file("your_files/report.pdf")
    assert restored is True
    assert target.is_file()
    assert target.read_bytes() == b"report bytes v1"
    
    # Registry must clear trashed_at
    rec_after = registry.get_by_path("your_files/report.pdf")
    assert rec_after is not None
    assert rec_after.trashed_at is None
    active_files_after = registry.list_files(include_trashed=False)
    assert any(f.path == "your_files/report.pdf" for f in active_files_after)

def test_trash_purge_expired(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "your_files" / "old.txt"
    target.parent.mkdir(parents=True)
    target.write_text("old")
    
    registry = FileIndexRegistry(db_path=tmp_path / "test.db")
    trash = TrashManager(workspace_root=workspace, registry=registry)
    
    trash.trash_file("your_files/old.txt")
    trash_dir = workspace.parent / ".trash" if workspace.name == "workspace" else workspace / ".trash"
    assert len(list(trash.trash_dir.glob("*.blob"))) == 1
    
    # Purge with TTL = 0 (immediately expire everything)
    purged = trash.purge_expired(ttl_seconds=-1)
    assert purged == 1
    assert len(list(trash.trash_dir.glob("*.blob"))) == 0
