"""Tests for Task 5: MemoryTactFirewall and ToolPitfallShield."""

from lca.cognition.memory.guards.firewall import MemoryTactFirewall
from lca.cognition.memory.types import SemanticClaim
from lca.infrastructure.tools.shield.tool_shield import ToolPitfallShield


def test_sensitive_memory_suppressed_in_irrelevant_turns():
    """敏感记忆在无关上下文严格 100% 遮蔽，在用户直接提问时放行。"""
    sensitive_claim = SemanticClaim(
        id="claim_sensitive_01",
        claim="父亲去世于2022年",
        confidence=1.0,
        sources=("dialogue_1",),
        valid_from=None,
        sensitivity="high",
    )
    normal_claim = SemanticClaim(
        id="claim_normal_01",
        claim="喜欢喝美式咖啡",
        confidence=1.0,
        sources=("dialogue_1",),
        valid_from=None,
        sensitivity="normal",
    )
    firewall = MemoryTactFirewall(memories=[sensitive_claim, normal_claim])

    # 1. 无关意图：查天气
    irrelevant_memories = firewall.filter_for_prompt(user_intent="今天北京天气怎么样？")
    joined_irrelevant = " ".join(irrelevant_memories)
    assert "去世" not in joined_irrelevant
    assert "美式咖啡" in joined_irrelevant

    # 2. 无关意图：写代码
    code_memories = firewall.filter_for_prompt(user_intent="帮我写一个 Python 正则表达式")
    assert "去世" not in " ".join(code_memories)

    # 3. 用户直接提问/询问变故
    direct_memories = firewall.filter_for_prompt(user_intent="我之前跟你提过我家里的变故吗？")
    joined_direct = " ".join(direct_memories)
    assert "去世" in joined_direct


def test_tact_firewall_detects_and_sanitizes_showoff_phrases():
    """声带契约（禁显摆）：检测并清洗‘我记得你说过’、‘根据我的记忆库’等监控感套话。"""
    firewall = MemoryTactFirewall()

    # 检测显摆套话
    assert firewall.contains_showoff_phrase("我记得你说过你对花生过敏，所以推荐这个") is True
    assert firewall.contains_showoff_phrase("根据我的长期记忆库记录，您在深圳做程序员") is True
    assert firewall.contains_showoff_phrase("深圳的科技公司非常多，推荐你看看南山区的岗位") is False

    # 清洗显摆套话
    sanitized = firewall.sanitize_response("我记得你说过你喜欢吃辣，推荐去川味馆。")
    assert "我记得你说过" not in sanitized
    assert "喜欢吃辣" in sanitized


def test_tool_pitfall_shield_injects_redlines():
    """工具避坑哨兵：调用前毫秒级提取 TOOLS.md 针对该工具的单行红线警示。"""
    tools_md = """# TOOLS.md
## 本机工具与避坑指南

### ssh
- 宿主机远程请优先使用 ssh252 别名，且禁依赖 /root 软链。

### bash
- 严禁执行 cd 命令，所有文件与目录路径必须使用绝对路径或 Cwd 参数。
"""
    shield = ToolPitfallShield.from_markdown(tools_md)

    # 验证命中 ssh
    guard_ssh = shield.get_pre_execution_guard("ssh")
    assert "ssh252" in guard_ssh
    assert "禁依赖 /root 软链" in guard_ssh

    # 验证命中 bash
    guard_bash = shield.get_pre_execution_guard("bash")
    assert "严禁执行 cd" in guard_bash

    # 验证未配置工具返回空字符串
    guard_curl = shield.get_pre_execution_guard("curl")
    assert guard_curl == ""


