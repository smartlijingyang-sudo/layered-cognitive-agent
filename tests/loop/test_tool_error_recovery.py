"""Loop-layer tool error recovery tests.

Covers:
- 可恢复错误重进 think: classified failure_kind → terminate_decide emits
  should_terminate=False (spec §7: USE_TOOL + failed Observation → think).
- N 次后 fail: ToolErrorBudget exhausts after N (default 3).
- 失败解释非空: build_failure_explanation always returns non-empty Chinese.
- tool_search._error carries failure_kind=validation (the run_fb8eb1140257 fix).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.harness.act.effect_receipt import EffectReceipt
from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.infrastructure.tool_defer.tool_search import _error as tool_search_error
from lca.loop.tool_error import (
    ToolErrorBudget,
    ToolErrorKind,
    build_failure_explanation,
    classify_tool_error,
    count_consecutive_tool_failures,
    find_terminal_tool_error,
)
from lca.nodes.act.observe.terminate_decide import ActObserveTerminateDecideExecutor


def _receipt(*, failure_kind: str | None, failed: bool = True) -> EffectReceipt:
    from lca.contracts.harness.act.effect_receipt import EffectOutcome

    return EffectReceipt(
        invocation_id="test-inv",
        idempotency_key="test-key",
        provider="test",
        outcome=EffectOutcome.FAILED if failed else EffectOutcome.SUCCEEDED,
        failure_kind=failure_kind,
        error_code="TEST_ERR" if failed else None,
    )


def _run(coro):
    return asyncio.run(coro)


def _terminate_decide(receipt: EffectReceipt) -> bool:
    from lca.contracts.protocols.declarative.declarative_1.node_executor import (
        NodeInput,
    )
    from lca.contracts.protocols.declarative.declarative_1.ports import PortName

    ex = ActObserveTerminateDecideExecutor()
    out = _run(ex.node_execute(None, NodeInput(port_values={PortName("receipt"): receipt})))
    return out.port_values[PortName("should_terminate")]


class TestClassify:
    def test_validation_errors_are_recoverable(self):
        assert classify_tool_error("tool_search: unknown tool namespace 'corp'") is ToolErrorKind.RECOVERABLE
        assert classify_tool_error("KeyError: 'foo'") is ToolErrorKind.RECOVERABLE
        assert classify_tool_error("参数校验失败") is ToolErrorKind.RECOVERABLE
        assert classify_tool_error("timeout after 30s") is ToolErrorKind.RECOVERABLE

    def test_auth_errors_are_fatal(self):
        assert classify_tool_error("401 Unauthorized") is ToolErrorKind.FATAL
        assert classify_tool_error("permission denied") is ToolErrorKind.FATAL
        assert classify_tool_error("会话过期，请重新登录") is ToolErrorKind.FATAL

    def test_unknown_defaults_recoverable(self):
        assert classify_tool_error("something weird happened") is ToolErrorKind.RECOVERABLE
        assert classify_tool_error(None) is ToolErrorKind.RECOVERABLE
        assert classify_tool_error("") is ToolErrorKind.RECOVERABLE


class TestBudget:
    def test_default_three_retries(self):
        b = ToolErrorBudget()
        assert b.note_recoverable_failure() is True   # 1
        assert b.note_recoverable_failure() is True   # 2
        assert b.note_recoverable_failure() is True   # 3
        assert b.note_recoverable_failure() is False  # 4th -> exhausted
        assert b.exhausted is True

    def test_configurable(self):
        b = ToolErrorBudget(max_recoverable_retries=1)
        assert b.note_recoverable_failure() is True
        assert b.note_recoverable_failure() is False

    def test_success_resets(self):
        b = ToolErrorBudget()
        b.note_recoverable_failure()
        b.note_recoverable_failure()
        b.note_success()
        assert b.consecutive_failures == 0
        assert b.exhausted is False


class TestExplanation:
    def test_non_empty_chinese(self):
        for kind in (ToolErrorKind.RECOVERABLE, ToolErrorKind.FATAL):
            text = build_failure_explanation(
                tool_name="tool_search", error_text="boom", attempts=1, kind=kind
            )
            assert text and isinstance(text, str)
            # contains Chinese
            assert any("\u4e00" <= ch <= "\u9fff" for ch in text)

    def test_mentions_tool_and_retry_count(self):
        text = build_failure_explanation(
            tool_name="mcp__corp__oa_my_tickets",
            error_text="unknown tool namespace 'corp'",
            attempts=3,
            kind=ToolErrorKind.RECOVERABLE,
        )
        assert "mcp__corp__oa_my_tickets" in text
        assert "3" in text

    def test_fatal_mentions_auth(self):
        text = build_failure_explanation(
            tool_name="oa_approve", error_text="401 Unauthorized",
            attempts=1, kind=ToolErrorKind.FATAL,
        )
        assert "权限" in text or "认证" in text


class TestToolSearchErrorClassification:
    def test_error_carries_validation_failure_kind(self):
        """run_fb8eb1140257 回归：tool_search 参数错误必须带分类，否则 terminate_decide 会杀 run。"""
        obs = tool_search_error("tool_search: unknown tool namespace 'corp'")
        assert obs.success is False
        assert obs.extra.get(FAILURE_KIND) == FAILURE_KIND_VALIDATION


class TestTerminateDecide:
    def test_classified_failure_does_not_terminate(self):
        """可恢复错误重进 think：带 failure_kind 分类的失败 → should_terminate=False。"""
        receipt = _receipt(failure_kind=FAILURE_KIND_VALIDATION, failed=True)
        assert _terminate_decide(receipt) is False

    def test_unclassified_failure_terminates(self):
        """未分类失败（host 派发失败）→ should_terminate=True（现有语义不变）。"""
        receipt = _receipt(failure_kind=None, failed=True)
        assert _terminate_decide(receipt) is True

    def test_success_never_terminates(self):
        receipt = _receipt(failure_kind=None, failed=False)
        assert _terminate_decide(receipt) is False


def _visit(outputs: dict) -> SimpleNamespace:
    return SimpleNamespace(node_id="test.node", outputs=outputs)


class TestVisitScan:
    def test_find_terminal_tool_error(self):
        visits = [
            _visit({"tool_a": {"tool_name": "tool_a", "success": True}}),
            _visit({"tool_b": {"tool_name": "tool_b", "success": False, "error": "boom"}}),
        ]
        assert find_terminal_tool_error(visits) == ("tool_b", "boom")

    def test_find_none_when_clean(self):
        visits = [_visit({"tool_a": {"tool_name": "tool_a", "success": True}})]
        assert find_terminal_tool_error(visits) == (None, None)
        assert find_terminal_tool_error([]) == (None, None)

    def test_count_consecutive(self):
        visits = [
            _visit({"t": {"tool_name": "tool_search", "success": False, "error": "e1"}}),
            _visit({"t": {"tool_name": "tool_search", "success": False, "error": "e2"}}),
            _visit({"t": {"tool_name": "tool_search", "success": False, "error": "e3"}}),
        ]
        assert count_consecutive_tool_failures(visits, "tool_search") == 3

    def test_count_stops_at_success(self):
        visits = [
            _visit({"t": {"tool_name": "tool_search", "success": False, "error": "old"}}),
            _visit({"t": {"tool_name": "tool_search", "success": True}}),
            _visit({"t": {"tool_name": "tool_search", "success": False, "error": "new"}}),
        ]
        # newest-first: 1 failure, then success breaks the streak
        assert count_consecutive_tool_failures(visits, "tool_search") == 1

    def test_count_stops_at_different_tool(self):
        visits = [
            _visit({"t": {"tool_name": "other", "success": False, "error": "x"}}),
            _visit({"t": {"tool_name": "tool_search", "success": False, "error": "y"}}),
        ]
        assert count_consecutive_tool_failures(visits, "tool_search") == 1
