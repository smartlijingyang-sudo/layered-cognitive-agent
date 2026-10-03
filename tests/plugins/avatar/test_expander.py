"""通用头像提示词扩写器契约与实现测试（消除硬编码，实现通用泛化）。

覆盖：
1. AST 反硬编码守卫：断言 expander.py 中绝对不存在特例人物字典；
2. RulePromptExpander 通用语法清理：对任意实体（爱因斯坦、鲁迅、赛博朋克猫、水墨剑客、墨镜柴犬）
   稳定剔除口语前缀，格式化为标准肖像模版；
3. LlmPromptExpander 通用 1-shot 提示词工程转换器：支持异步/同步 LLM 并具备自动容错回退。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from lca.plugins.avatar.expander import (
    LlmPromptExpander,
    PromptExpander,
    RulePromptExpander,
)

_EXPANDER_PATH = (
    Path(__file__).resolve().parents[3] / "lca" / "plugins" / "avatar" / "expander.py"
)


def test_expander_has_zero_hardcoded_figures() -> None:
    """AST 守卫：断言 expander.py 绝不包含任何写死的人物/实体名单或字典。"""
    tree = ast.parse(_EXPANDER_PATH.read_text(encoding="utf-8"))
    forbidden_names = {"_KNOWN_FIGURE_MAP", "FIGURE_MAP", "KNOWN_FIGURES", "FAMOUS_PEOPLE"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            pytest.fail(f"Found forbidden hardcoded figure identifier in expander.py: {node.id}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "弗洛伊德" not in node.value, "Found hardcoded figure Freud in expander.py"
            assert "爱因斯坦" not in node.value, "Found hardcoded figure Einstein in expander.py"


@pytest.mark.parametrize(
    ("raw_input", "expected_subject"),
    [
        ("我想修改你的形象和头像，改成：弗洛伊德", "弗洛伊德"),
        ("请帮我换成一个赛博朋克风格的猫咪侦探", "赛博朋克风格的猫咪侦探"),
        ("换成爱因斯坦", "爱因斯坦"),
        ("把头像修改为：水墨风武侠剑客", "水墨风武侠剑客"),
        ("做个戴墨镜的柴犬", "戴墨镜的柴犬"),
        ("帮我画一个未来宇航员", "未来宇航员"),
        ("换个夏日海滩风", "夏日海滩风"),
        ("想要鲁迅先生的木刻版画风格头像", "鲁迅先生的木刻版画风格头像"),
        ("达芬奇", "达芬奇"),
        ("Cyberpunk anime hacker", "Cyberpunk anime hacker"),
    ],
)
@pytest.mark.asyncio
async def test_rule_expander_cleans_conversational_prefixes_and_generates_template(
    raw_input: str, expected_subject: str
) -> None:
    expander = RulePromptExpander()
    assert isinstance(expander, PromptExpander)
    prompt = await expander.expand(raw_input)
    assert expected_subject in prompt
    assert "Close-up avatar portrait of " in prompt
    assert "centered composition" in prompt
    assert "我想" not in prompt
    assert "请帮我" not in prompt
    assert "改成：" not in prompt


@pytest.mark.asyncio
async def test_rule_expander_strips_punctuation_and_whitespace() -> None:
    expander = RulePromptExpander()
    prompt = await expander.expand("   改成：   爱因斯坦！！！  ")
    assert "Close-up avatar portrait of 爱因斯坦" in prompt


@pytest.mark.asyncio
async def test_llm_expander_with_async_callable() -> None:
    async def fake_llm(req: str) -> str:
        return f"Artistic oil portrait of {req}, impressionist style"

    expander = LlmPromptExpander(llm=fake_llm)
    res = await expander.expand("Van Gogh")
    assert res == "Artistic oil portrait of Van Gogh, impressionist style"


@pytest.mark.asyncio
async def test_llm_expander_with_sync_callable() -> None:
    def fake_llm(req: str) -> str:
        return f"Hyperrealistic render of {req}"

    expander = LlmPromptExpander(llm=fake_llm)
    res = await expander.expand("Futuristic Android")
    assert res == "Hyperrealistic render of Futuristic Android"


@pytest.mark.asyncio
async def test_llm_expander_falls_back_to_rule_on_error() -> None:
    def failing_llm(req: str) -> str:
        raise RuntimeError("LLM service unavailable")

    expander = LlmPromptExpander(llm=failing_llm)
    res = await expander.expand("我想换成赛博朋克猫咪")
    # 优雅回退到 RulePromptExpander
    assert "Close-up avatar portrait of 赛博朋克猫咪" in res
    assert "centered composition" in res
