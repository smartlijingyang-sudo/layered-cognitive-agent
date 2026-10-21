import pytest
from pathlib import Path
from lca.plugins.prompts.sections.filesystem import FilesystemPromptSection
from lca.contracts.models.core.workspace.file_record import FileRecord, ReadabilityTier, VisibilityTier

def test_filesystem_prompt_section_rendering():
    files = [
        FileRecord(
            file_id="f1",
            path="user/报价单.xlsx",
            origin="upload",
            visibility=VisibilityTier.INTERNAL,
            size_bytes=19000,
            readability=ReadabilityTier.CONVERTED,
        )
    ]
    section = FilesystemPromptSection(uploaded_files=files)
    output = section.render()
    rendered = output.text

    assert "## Filesystem" in rendered
    assert "~/workspace/your_files/" in rendered
    assert "~/workspace/goals/<goal-slug>/files/" in rendered
    assert "~/workspace/goals/<goal-slug>/hidden_files/" in rendered
    assert "~/workspace/user/" in rendered
    assert "sandbox://workspace/path" in rendered
    assert "/mnt/data/user/报价单.xlsx" in rendered
    assert "converted" in rendered

def test_constitution_storage_invariants_present():
    constitution_path = Path(__file__).parents[3] / "lca" / "plugins" / "assistant" / "templates" / "CONSTITUTION.md"
    content = constitution_path.read_text(encoding="utf-8")
    assert "### Storage & Workspace Invariant" in content
    assert "SSOT Workspace" in content
    assert "Write-in-Place" in content
    assert "Persistence Tiers" in content
