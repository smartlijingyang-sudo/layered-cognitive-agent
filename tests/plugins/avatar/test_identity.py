"""Avatar 身份读取与 traits 摘要测试（Task 4）。

覆盖：
- 无 LLM 时确定性 fallback 非空；
- 提供 LLM callable 时直接透传其结果；
- ``load_identity`` 从临时 assistant home 聚合 profile.json / IDENTITY.md / SOUL.md。
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.plugins.avatar.identity import load_identity, summarize_traits


def test_summarize_fallback_without_llm():
    identity = "名称: 小助\n简介: 架构助手\n性格: 严谨、温暖"
    traits = summarize_traits(identity, llm=None)
    assert "小助" in traits or "架构助手" in traits or "严谨" in traits


def test_summarize_uses_llm_when_provided():
    def fake_llm(_: str) -> str:
        return "sharp, warm, cyberpunk"

    assert summarize_traits("x", llm=fake_llm) == "sharp, warm, cyberpunk"


def test_summarize_fallback_non_empty_for_blank_identity():
    assert summarize_traits("", llm=None) == "default assistant"


def test_load_identity_reads_profile_identity_and_soul(tmp_path: Path):
    home = tmp_path / "asst_1"
    home.mkdir()
    (home / "profile.json").write_text(
        json.dumps({"name": "小助", "description": "架构助手", "emoji": "🦉"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (home / "IDENTITY.md").write_text("# IDENTITY.md\n\navatar: 🦉\n", encoding="utf-8")
    (home / "SOUL.md").write_text(
        "# SOUL\n\n## 🧠 身份\n你是架构助手。\n\n## 🎭 性格\n严谨、温暖\n\n## 🗣 语气\n简洁直接。\n",
        encoding="utf-8",
    )

    identity = load_identity(home)

    assert "名称: 小助" in identity
    assert "简介: 架构助手" in identity
    assert "emoji: 🦉" in identity
    assert "avatar: 🦉" in identity
    assert "你是架构助手" in identity
    assert "严谨" in identity
    assert "简洁直接" in identity
