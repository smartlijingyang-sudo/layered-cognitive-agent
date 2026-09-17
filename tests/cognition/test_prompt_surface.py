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


def test_render_tools_block_emits_full_sandbox_when_tools_present() -> None:
    surface = PromptSurface.default()
    with patch(
        "lca.cognition.brain.prompt.surface.build_cloud_sandbox_prompt",
        return_value="X" * 300,
    ):
        rendered = surface.render_tools_block(
            (_Tool("executeCode", "Run code"),),
        )
    assert rendered.include_full_sandbox is True
    assert len(rendered.sandbox_block) > 200
    assert rendered.tool_count == 1


def test_render_tools_block_omits_sandbox_when_no_tools() -> None:
    surface = PromptSurface.default()
    rendered = surface.render_tools_block(())
    assert rendered.include_full_sandbox is False
    assert rendered.sandbox_block == ""
    # The native tool_calls schemas are the SSOT for availability; an empty
    # catalog renders nothing rather than asserting the opposite of the wire.
    assert rendered.tools_xml == ""
    assert rendered.body == ""
