"""Test CronUpcomingPanel upgrade for full editing, deletion, and execution (Task 6)."""

from pathlib import Path


def test_cron_upcoming_panel_contains_advanced_controls():
    here = Path(__file__).resolve().parents[3] / "deploy" / "lobehub" / "patches" / "ui"
    panel_source = here / "CronUpcomingPanel.tsx"
    assert panel_source.is_file(), f"Missing {panel_source}"
    content = panel_source.read_text(encoding="utf-8")

    # Invariants for Task 6
    assert "Switch" in content, "Must have Switch for enabled toggle"
    assert "Popconfirm" in content, "Must have Popconfirm for safe deletion"
    assert "handleRunNow" in content or "run" in content.lower(), "Must have run-now trigger"
    assert "handleDelete" in content or "delete" in content.lower(), "Must have delete handler"
    assert "Modal" in content, "Must have Modal for full editing/creation"
    assert "DatePicker" in content, "Must have DatePicker for time adjustments"


def test_cron_upcoming_panel_patch_meta():
    from deploy.lobehub.patches.ui.cron_upcoming_panel import meta

    assert meta.name == "cron_upcoming_panel"
    assert "src/features/Conversation/components/CronUpcomingPanel.tsx" in meta.files
