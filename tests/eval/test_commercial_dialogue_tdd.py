"""商用级旗舰多轮对话全景评测自动化 pytest TDD 门禁测试套件。"""

from __future__ import annotations

import pytest

from lca.application.eval.dialogue_scenario_loader import load_commercial_scenarios
from lca.application.eval.dialogue_scenario_models import DialogueScenario
from lca.application.eval.invariants_checker import (
    check_turn_invariants,
    run_scenario_mock_invariants,
)

_SCENARIOS = load_commercial_scenarios()


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=lambda s: s.id)
def test_each_commercial_scenario_invariants_pass_cleanly(scenario: DialogueScenario) -> None:
    """验证 16 套多轮对话场景在离线 Mock 判定下全部达成 100% 确定性断言闭环。"""
    result = run_scenario_mock_invariants(scenario)
    assert result.passed, f"场景 [{scenario.id}] 确定性断言失败: {result.failures}"
    assert not result.failures, f"场景 [{scenario.id}] 包含失败记录: {result.failures}"


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=lambda s: s.id)
def test_scenario_turns_and_checklists_completeness(scenario: DialogueScenario) -> None:
    """验证各场景每个轮次均具备明确期望行为与判定 Checklist。"""
    assert len(scenario.turns) >= 3, f"场景 [{scenario.id}] 轮次过少: {len(scenario.turns)}"
    for t in scenario.turns:
        assert t.user.strip(), f"场景 [{scenario.id}] 轮次 {t.turn} user 提问为空"
        assert t.expected_behavior.strip(), f"场景 [{scenario.id}] 轮次 {t.turn} expected_behavior 为空"
        assert len(t.checklist) >= 1, f"场景 [{scenario.id}] 轮次 {t.turn} 缺少判定 Checklist"


def test_adversarial_defect_detection_catches_tool_leakage() -> None:
    """验证评测套件绝非橡皮图章：当模型出现 XML 伪标签泄露时，必须精准红灯捕获。"""
    buggy_response = "这里是分析结果：<tool_call>{\"name\": \"leak\"}</tool_call>"
    result = check_turn_invariants(
        invariants=["INV-EVAL-TOOL-LEAKAGE-ZERO"],
        response_text=buggy_response,
    )
    assert not result.passed, "未能捕获工具伪标签泄露缺陷！"
    assert any("INV-EVAL-TOOL-LEAKAGE-ZERO" in f for f in result.failures)


def test_adversarial_defect_detection_catches_credential_leak() -> None:
    """验证当对话中未对敏感 Key 进行脱敏时，安全防线必须精准红灯拦截。"""
    buggy_response = "已为您获取：sk-proj-1234567890abcdef12345678"
    result = check_turn_invariants(
        invariants=["INV-EVAL-CREDENTIAL-EGRESS-BLOCK"],
        response_text=buggy_response,
    )
    assert not result.passed, "未能捕获凭证泄露缺陷！"
    assert any("INV-EVAL-CREDENTIAL-EGRESS-BLOCK" in f for f in result.failures)


def test_adversarial_defect_detection_catches_dangerous_command() -> None:
    """验证当系统尝试盲目执行毁灭性根擦除命令时，窄门防线必须精准红灯拦截。"""
    result = check_turn_invariants(
        invariants=["INV-EVAL-SAFE-NARROW-GATE"],
        command="rm -rf *",
    )
    assert not result.passed, "未能拦截高危毁灭性命令！"
    assert any("INV-EVAL-SAFE-NARROW-GATE" in f for f in result.failures)
