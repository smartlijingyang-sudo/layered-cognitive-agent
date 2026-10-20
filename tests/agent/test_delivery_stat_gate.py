import pytest
from pathlib import Path
from lca.runtime.delivery.delivery_gate import (
    verify_delivery_attachments,
    DeliveryVerificationError,
    DeliverySecurityError,
    extract_delivery_links,
)

def test_extract_delivery_links():
    text = (
        "Here is the report:\n"
        "![Report](sandbox://workspace/your_files/report.pdf)\n"
        "Also plan:\n"
        "[Plan](sandbox://workspace/goals/growth/files/plan.md)"
    )
    links = extract_delivery_links(text)
    assert len(links) == 2
    assert links[0] == "your_files/report.pdf"
    assert links[1] == "goals/growth/files/plan.md"

def test_delivery_gate_blocks_missing_or_tmp_files(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "your_files").mkdir()
    (workspace / "your_files" / "real.pdf").write_bytes(b"content")
    
    # 1. Valid delivery with existing file passes
    valid_text = "Here is your plan: ![Plan](sandbox://workspace/your_files/real.pdf)"
    assert verify_delivery_attachments(valid_text, workspace_root=workspace) is True
    
    # 2. Missing file delivery raises DeliveryVerificationError
    fake_text = "Generated: ![Fake](sandbox://workspace/your_files/ghost.pdf)"
    with pytest.raises(DeliveryVerificationError) as exc_info:
        verify_delivery_attachments(fake_text, workspace_root=workspace)
    assert "ghost.pdf" in str(exc_info.value)
        
    # 3. Ephemeral /tmp leak raises DeliverySecurityError
    tmp_leak_text = "Here: ![Temp](sandbox://workspace//tmp/scratch.pdf)"
    with pytest.raises(DeliverySecurityError):
        verify_delivery_attachments(tmp_leak_text, workspace_root=workspace)

    # 4. Ephemeral naked /tmp link raises DeliverySecurityError
    tmp_leak_naked = "Here: [Temp](/tmp/scratch.pdf)"
    with pytest.raises(DeliverySecurityError):
        verify_delivery_attachments(tmp_leak_naked, workspace_root=workspace)
