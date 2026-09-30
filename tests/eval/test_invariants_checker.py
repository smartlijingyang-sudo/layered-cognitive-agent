"""验证确定性中间态断言与规则清单裁判引擎。"""

from __future__ import annotations

import pytest

from lca.application.eval.dialogue_scenario_loader import load_commercial_scenarios
from lca.application.eval.invariants_checker import (
    InvariantCheckResult,
    InvariantViolationError,
    assert_credential_not_leaked,
    assert_provenance_syntax,
    assert_safe_narrow_gate,
    assert_write_before_reply,
    assert_zero_tool_leakage,
    check_turn_invariants,
    run_scenario_mock_invariants,
)


def test_zero_tool_leakage_passes_for_clean_text() -> None:
    clean_text = "李超架构师您好，已为您完成微服务拆分方案。"
    assert_zero_tool_leakage(clean_text)


def test_zero_tool_leakage_fails_for_pseudo_xml() -> None:
    leaked_samples = [
        '<tool_call>{"name": "search"}</tool_call>',
        '<tool name="create_assistant_skill">args</tool>',
        '<delegate_to name="guanlan">review</delegate_to>',
        "<|tool_calls|>something",
    ]
    for sample in leaked_samples:
        with pytest.raises(InvariantViolationError):
            assert_zero_tool_leakage(f"回答内容：{sample} 结束")


def test_provenance_syntax_validation() -> None:
    valid = "- 饮食禁忌。 This came from 用户李超 when 初始设定健康禁忌, recorded 2026-09-30."
    assert_provenance_syntax(valid)

    invalid = "- 饮食禁忌。 纯文本记录无出生证明"
    with pytest.raises(InvariantViolationError):
        assert_provenance_syntax(invalid)


def test_credential_not_leaked_validation() -> None:
    clean = "DB_URL=postgresql://admin:***@db.internal, OPENAI_API_KEY=sk-proj-***"
    assert_credential_not_leaked(clean)

    leaked = "这里是凭证：sk-proj-998877665544332211AABBCCDDEEFF"
    with pytest.raises(InvariantViolationError):
        assert_credential_not_leaked(leaked)


def test_safe_narrow_gate_validation() -> None:
    safe = "rm -rf build/dist"
    assert_safe_narrow_gate(safe)

    dangerous = "rm -rf *"
    with pytest.raises(InvariantViolationError):
        assert_safe_narrow_gate(dangerous)


def test_write_before_reply_validation() -> None:
    assert_write_before_reply(100.0, 100.5)
    assert_write_before_reply(100.0, 100.0)

    with pytest.raises(InvariantViolationError):
        assert_write_before_reply(101.0, 100.0)


def test_check_turn_invariants_aggregated() -> None:
    result = check_turn_invariants(
        invariants=["INV-EVAL-TOOL-LEAKAGE-ZERO", "INV-EVAL-CREDENTIAL-EGRESS-BLOCK"],
        response_text="干净回复，无任何泄露",
    )
    assert result.passed
    assert not result.failures


def test_run_scenario_mock_invariants_for_all_scenarios() -> None:
    scenarios = load_commercial_scenarios()
    assert len(scenarios) == 16
    for sc in scenarios:
        res = run_scenario_mock_invariants(sc)
        assert isinstance(res, InvariantCheckResult)
        assert res.passed, f"场景 {sc.id} mock 校验失败: {res.failures}"
