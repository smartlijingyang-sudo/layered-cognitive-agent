"""ADR-clean-truths 决策 一:PhaseExecutionFailure.error_kind 与 machine-readable summary。

- PhaseExecutionFailure 自动从 attempts[-1].category 推导 error_kind
  (timeout → "timeout", transient → "provider", 其他 → "internal")。
- phase_failure_stop_result 把 error_kind 写入 RunDiagnostic.extra,
  并把 message 改为机读摘要 ``node={...} error_kind={...} attempts=N[...]``。
- message 不再是"The agent could not complete a required {node} step after {n} attempt(s)."。
"""

from __future__ import annotations

from lca.contracts.protocols.declarative.declarative_execution import (
    PhaseAttemptFailure,
    PhaseExecutionFailure,
)
from lca.plugins.phase_graph.failure_stop import (
    _summarize_attempts,
    phase_failure_stop_result,
)


def test_error_kind_derived_from_timeout_category() -> None:
    """两次 TimeoutError → outer error_kind='timeout'。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(
            PhaseAttemptFailure(attempt=1, category="timeout", error_type="TimeoutError"),
            PhaseAttemptFailure(attempt=2, category="timeout", error_type="TimeoutError"),
        ),
    )
    assert failure.error_kind == "timeout"


def test_error_kind_derived_from_transient_category() -> None:
    """transient 归类为 provider。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(
            PhaseAttemptFailure(attempt=1, category="transient", error_type="ConnectionError"),
        ),
    )
    assert failure.error_kind == "provider"


def test_error_kind_derived_from_permanent_category() -> None:
    """permanent 归类为 internal。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(PhaseAttemptFailure(attempt=1, category="permanent", error_type="RuntimeError"),),
    )
    assert failure.error_kind == "internal"


def test_error_kind_can_be_overridden_explicitly() -> None:
    """显式传入可覆盖推导。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(PhaseAttemptFailure(attempt=1, category="timeout", error_type="TimeoutError"),),
        error_kind="contract",
    )
    assert failure.error_kind == "contract"


def test_summarize_attempts_is_machine_readable() -> None:
    """摘要格式固定,含 node= / error_kind= / attempts= 三段。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(
            PhaseAttemptFailure(attempt=1, category="timeout", error_type="TimeoutError"),
            PhaseAttemptFailure(attempt=2, category="timeout", error_type="TimeoutError"),
        ),
    )
    summary = _summarize_attempts(failure)
    assert summary.startswith("node=think.main "), summary
    assert "error_kind=timeout" in summary, summary
    assert "attempts=2" in summary, summary
    assert "1:timeout:TimeoutError" in summary, summary
    assert "2:timeout:TimeoutError" in summary, summary
    # 验证不再含旧文学化句式
    assert "the agent could not complete" not in summary.lower()
    assert "step after" not in summary.lower()


def test_phase_failure_stop_result_carries_error_kind_in_extra() -> None:
    """StopDecision.failure.extra 应含 (error_kind, value)。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(
            PhaseAttemptFailure(attempt=1, category="timeout", error_type="TimeoutError"),
            PhaseAttemptFailure(attempt=2, category="timeout", error_type="TimeoutError"),
        ),
    )
    res = phase_failure_stop_result(failure, plan_ref="p", run_id="r", trace_id="t")
    stop = res.payload
    extra_dict = dict(stop.failure.extra)
    assert extra_dict.get("error_kind") == "timeout", extra_dict


def test_phase_failure_stop_result_message_is_machine_readable() -> None:
    """StopDecision.failure.message 是机读摘要而非文学化句式。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(
            PhaseAttemptFailure(attempt=1, category="timeout", error_type="TimeoutError"),
            PhaseAttemptFailure(attempt=2, category="timeout", error_type="TimeoutError"),
        ),
    )
    res = phase_failure_stop_result(failure, plan_ref="p", run_id="r", trace_id="t")
    stop = res.payload
    msg = stop.failure.message
    assert "node=think.main" in msg
    assert "attempts=2" in msg
    # 关键:不再含旧长句开头
    assert not msg.startswith("The agent could not complete"), msg


def test_failure_message_appends_root_cause_when_captured() -> None:
    """捕获到上游错误原文时,展示串 = 机读标签 + `` | `` + 根因。"""
    root = "Client error '429 Too Many Requests' for url 'https://provider.example/v1/messages'"
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(
            PhaseAttemptFailure(
                attempt=1,
                category="permanent",
                error_type="HTTPStatusError",
                error_message=root,
            ),
        ),
    )
    res = phase_failure_stop_result(failure, plan_ref="p", run_id="r", trace_id="t")
    msg = res.payload.failure.message
    assert msg.startswith("node=think.main ")
    assert "error_kind=internal" in msg
    assert msg.endswith(f"| {root}")
    # attempts summaries 同步携带每次 attempt 的原文
    assert res.payload.failure.attempts[0].message == root


def test_failure_message_has_no_suffix_without_root_cause() -> None:
    """未捕获原文时保持纯机读标签,不追加尾缀。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(PhaseAttemptFailure(attempt=1, category="timeout", error_type="TimeoutError"),),
    )
    res = phase_failure_stop_result(failure, plan_ref="p", run_id="r", trace_id="t")
    msg = res.payload.failure.message
    assert " | " not in msg
    assert msg == _summarize_attempts(failure)
    assert res.payload.failure.attempts[0].message is None


def test_failure_message_prefers_latest_attempt_with_root_cause() -> None:
    """多次 attempt 时取最后一次携带原文的作为终态根因。"""
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(
            PhaseAttemptFailure(
                attempt=1,
                category="transient",
                error_type="ConnectionError",
                error_message="first failure",
            ),
            PhaseAttemptFailure(
                attempt=2,
                category="transient",
                error_type="ConnectionError",
                error_message="second failure",
            ),
        ),
    )
    res = phase_failure_stop_result(failure, plan_ref="p", run_id="r", trace_id="t")
    assert res.payload.failure.message.endswith("| second failure")


def test_frontend_display_string_carries_label_and_root_cause() -> None:
    """前端展示链:合成串经 format_user_error 后同时含分类标签与上游根因。

    reducer 对 ``stop.failure.message`` 是透传(见
    tests/test_run_diagnostic.py::test_reducer_apply_stop_propagates_diagnostic_message),
    故此处直接验证 failure_stop 合成串到前端格式化函数的完整投影。
    """
    from lca.plugins.transport.webserver.handlers.runs.observability.error_presentation import (
        format_user_error,
    )

    root = "Client error '429 Too Many Requests' for url 'https://provider.example/v1/messages'"
    failure = PhaseExecutionFailure(
        node_id="think.main",
        attempts=(
            PhaseAttemptFailure(
                attempt=1,
                category="permanent",
                error_type="HTTPStatusError",
                error_message=root,
            ),
        ),
    )
    res = phase_failure_stop_result(failure, plan_ref="p", run_id="r", trace_id="t")
    displayed = format_user_error(res.payload.failure.message, run_id="r", trace_id="t")
    assert "node=think.main" in displayed
    assert root in displayed
