"""PromptSurface SSOT tests (ADR-0196)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from lca.cognition.brain.prompt.surface import PromptSurface


@dataclass(frozen=True)
class _Tool:
    name: str
    description: str = ""


def test_render_tools_xml_uses_fc_tools_not_empty_catalog() -> None:
    surface = PromptSurface.default()
    xml = surface.render_tools_xml((_Tool("executeCode", "Run code"),))
    assert "executeCode" in xml
    assert "（无可用工具）" not in xml


def test_informative_text_uses_concise_sandbox() -> None:
    surface = PromptSurface.default()
    rendered = surface.render_tools_block(
        (_Tool("executeCode", "Run code"),),
        task="用python写一个图计划的笑话",
    )
    assert rendered.task_class == "informative_text"
    assert rendered.include_full_sandbox is False
    assert "Prefer a direct text reply" in rendered.sandbox_block
    assert "executeCode" in rendered.tools_xml


def test_visual_task_includes_full_sandbox_when_tools_present() -> None:
    surface = PromptSurface.default()
    with patch(
        "lca.cognition.brain.prompt.surface.build_cloud_sandbox_prompt",
        return_value="X" * 300,
    ):
        rendered = surface.render_tools_block(
            (_Tool("executeCode", "Run code"),),
            task="画一张 matplotlib 饼图",
        )
    assert rendered.task_class == "visual_artifact"
    assert rendered.include_full_sandbox is True
    assert len(rendered.sandbox_block) > 200
