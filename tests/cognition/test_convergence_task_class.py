"""Task classification tests (ADR-0196)."""

from __future__ import annotations

from lca.cognition.convergence.task_class import classify_task


def test_joke_task_is_informative_text() -> None:
    assert classify_task("用python写一个图计划的笑话") == "informative_text"


def test_plot_task_is_visual() -> None:
    assert classify_task("用 matplotlib 画一张饼图") == "visual_artifact"
