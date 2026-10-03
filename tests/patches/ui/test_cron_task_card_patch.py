"""Test cron_task_card_widget patch and CronTaskCard component (Task 5)."""

from pathlib import Path


def test_cron_task_card_component_file_exists():
    here = Path(__file__).resolve().parents[3] / "deploy" / "lobehub" / "patches" / "ui"
    card_source = here / "CronTaskCard.tsx"
    assert card_source.is_file(), f"Missing {card_source}"
    content = card_source.read_text(encoding="utf-8")
    assert "CronTaskCard" in content
    assert "snooze" in content.lower()
    assert "delete" in content.lower()
    assert "edit" in content.lower()


def test_cron_task_card_patch_meta():
    from deploy.lobehub.patches.ui.cron_task_card_widget import meta

    assert meta.name == "cron_task_card_widget"
    assert "src/features/Conversation/Messages/components/CronTaskCard.tsx" in meta.files
    assert "src/features/Conversation/Messages/Assistant/index.tsx" in meta.files
