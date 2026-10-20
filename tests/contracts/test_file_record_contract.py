import pytest
from datetime import datetime, timezone
from lca.contracts.models.core.workspace.file_record import (
    FileRecord,
    ReadabilityTier,
    VisibilityTier,
    derive_visibility,
    classify_readability,
    to_sandbox_uri,
)

def test_derive_visibility():
    assert derive_visibility("your_files/report.pdf") == VisibilityTier.USER
    assert derive_visibility("goals/growth/files/summary.md") == VisibilityTier.USER
    assert derive_visibility("goals/growth/hidden_files/seen.json") == VisibilityTier.INTERNAL
    assert derive_visibility("user/doc.xlsx") == VisibilityTier.INTERNAL
    assert derive_visibility(".trash/old.txt") == VisibilityTier.INTERNAL

def test_classify_readability():
    assert classify_readability("test.py", "text/x-python") == ReadabilityTier.NATIVE
    assert classify_readability("sheet.xlsx", "application/vnd.openxmlformats") == ReadabilityTier.CONVERTED
    assert classify_readability("chart.png", "image/png") == ReadabilityTier.VISUAL
    assert classify_readability("app.bin", "application/octet-stream") == ReadabilityTier.OPAQUE

def test_to_sandbox_uri():
    assert to_sandbox_uri("your_files/plan.pdf") == "sandbox://workspace/your_files/plan.pdf"
    assert to_sandbox_uri("/mnt/data/your_files/plan.pdf") == "sandbox://workspace/your_files/plan.pdf"

def test_file_record_instantiation():
    record = FileRecord(
        file_id="file_123456",
        path="your_files/analysis.pdf",
        origin="agent_created",
        visibility=derive_visibility("your_files/analysis.pdf"),
        mime="application/pdf",
        size_bytes=1024,
        readability=classify_readability("analysis.pdf", "application/pdf"),
    )
    assert record.visibility == VisibilityTier.USER
    assert record.readability == ReadabilityTier.CONVERTED
    assert record.size_bytes == 1024
