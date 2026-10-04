"""URL 铁律回归：react_tool_usage_guidelines 渲染文本必须包含 URL 铁律三句。"""

from __future__ import annotations

from lca.plugins.prompts.sections.plugin import Config
from lca.plugins.prompts.sections.text import build_react_tool_usage


def _render_default_text() -> str:
    section = build_react_tool_usage(Config())
    out = section.render(role_profile=None, tools=())  # type: ignore[arg-type]
    return out.text


def test_section_renders_tool_usage_block() -> None:
    text = _render_default_text()
    assert "<tool_usage_guidelines>" in text
    assert "react_tool_usage" not in text  # section 名不进正文


def test_url_iron_rule_no_assembled_url() -> None:
    text = _render_default_text()
    assert "URL 铁律" in text
    assert "严禁凭记忆或参数知识拼装 URL" in text


def test_tool_returned_url_verbatim() -> None:
    text = _render_default_text()
    assert "照单全信" in text
    assert "先用工具验证" in text


def test_token_url_only_to_user() -> None:
    text = _render_default_text()
    assert "只发给用户本人" in text
