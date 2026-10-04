"""URL 铁律守卫：prompt 规则不许硬编码在 py 里，必须进 Tier-1 PLATFORM.md 常驻 md（5098195a0 起，不在 repo 内，由部署落盘）。"""

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
    # 5098195a0：中文行改为英文措辞，语义不变
    assert "Identity first" in _REACT_TOOL_USAGE_TEXT
    assert "account identity" in _REACT_TOOL_USAGE_TEXT
