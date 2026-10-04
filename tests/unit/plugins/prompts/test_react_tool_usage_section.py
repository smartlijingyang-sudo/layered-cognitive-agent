"""URL 铁律守卫：prompt 规则不许硬编码在 py 里，必须进 contextfiles 常驻 md（CONSTITUTION.md）。"""

from __future__ import annotations

from lca.plugins.prompts.sections.text import (
    _REACT_TOOL_USAGE_TEXT,
    _REACT_TOOL_USAGE_TEXT_GATED,
)

_FORBIDDEN_FRAGMENTS = (
    "URL 铁律",
    "拼装 URL",
    "脑补或拼装",
    "照单全信",
    "只发给用户本人",
)


def test_no_url_rules_hardcoded_in_py() -> None:
    for fragment in _FORBIDDEN_FRAGMENTS:
        assert fragment not in _REACT_TOOL_USAGE_TEXT, fragment
        assert fragment not in _REACT_TOOL_USAGE_TEXT_GATED, fragment


def test_identity_disclosure_line_stays() -> None:
    assert "动身份先报身份" in _REACT_TOOL_USAGE_TEXT
