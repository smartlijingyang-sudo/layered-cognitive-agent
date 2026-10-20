import pytest
from pathlib import Path
from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter
from lca.contracts.models.core.execution.sandbox import SessionConfig

@pytest.mark.asyncio
async def test_sandbox_mounts_persistent_workspace_directly(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = LocalSandboxAdapter(root=str(workspace))
    
    # Session creation with workspace_root
    config = SessionConfig(workspace_root=str(workspace))
    session = await adapter.create_session(config=config)
    assert session is not None
    
    paths = adapter._paths_for(session.session_id)
    # The session host root MUST be the workspace itself, NOT an ephemeral .sessions subdir
    assert paths.host_root == workspace
    assert not (workspace / ".sessions").exists()
    
    # Required canonical directory structure must be initialized
    assert (workspace / "your_files").is_dir()
    assert (workspace / "user").is_dir()
    assert (workspace / "outputs").is_dir()

@pytest.mark.asyncio
async def test_cross_session_write_in_place_continuity(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = LocalSandboxAdapter(root=str(workspace))
    
    # Session 1: Write a file to /mnt/data/your_files/report.txt
    config = SessionConfig(workspace_root=str(workspace))
    sess1 = await adapter.create_session(config=config)
    code_write = (
        "with open('/mnt/data/your_files/report.txt', 'w') as f:\n"
        "    f.write('report content v1')\n"
    )
    res1 = await adapter.run_in_session(sess1.session_id, code_write)
    assert res1.success
    
    # Host workspace immediately has the file
    assert (workspace / "your_files" / "report.txt").read_text() == "report content v1"
    
    # Session 2 (Next turn): Can read the file from /mnt/data/your_files/report.txt
    sess2 = await adapter.create_session(config=config)
    code_read = (
        "with open('/mnt/data/your_files/report.txt') as f:\n"
        "    print(f.read())\n"
    )
    res2 = await adapter.run_in_session(sess2.session_id, code_read)
    assert res2.success
    assert "report content v1" in res2.stdout
