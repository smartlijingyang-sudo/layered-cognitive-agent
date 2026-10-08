"""ADR-0158 决策 三/四:AgentState.final_output 字段删除 + 读取方迁移到 TerminalOutcome。

约束:
- AgentState 不再有 final_output 字段
- state.py 源文件不含 final_output 字段定义
- reducer.py / agent_state.py / stop_policy.py 等读取方迁移到
  TerminalOutcome.final_output_ref(ADR-0077)
"""

from __future__ import annotations


def test_agent_state_has_no_final_output_field() -> None:
    """ADR-0158 决策 四:AgentState.final_output 字段必须删除。"""

    from lca.contracts.models.core.state.state import AgentState

    assert "final_output" not in AgentState.__annotations__, (
        "AgentState.final_output 字段必须删除(ADR-0158 决策 四);"
        "事实答案改走 TerminalOutcome.final_output_ref(ADR-0077)"
    )


def test_state_module_does_not_declare_final_output() -> None:
    """state.py 源文件不含 final_output 字段定义/默认。"""

    from lca.contracts.models.core import state as state_module

    src = state_module.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    # 检查 dataclass 字段声明形式
    assert "final_output: " not in body, (
        "state.py 源文件仍含 final_output 字段定义(ADR-0158 决策 四)"
    )


def test_runtime_reducer_does_not_read_state_final_output() -> None:
    """reducer.py 代码段不含 state.final_output 引用。"""

    # NOTE (round-0344): canonical path since 74e827d9a bulk shim deletion.
    from lca.plugins.loop.reducer import plugin as reducer_module

    src = reducer_module.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    code_lines = [line for line in body.splitlines() if not line.lstrip().startswith("#")]
    code_body = "\n".join(code_lines)
    # state.final_output / state.final_output = ... 全部不允许
    assert "state.final_output" not in code_body, (
        "reducer.py 代码段仍读 state.final_output(ADR-0158 决策 四)"
    )


def test_harness_projection_agent_state_does_not_write_final_output() -> None:
    """agent_state.py 代码段不含 state.final_output = ... 写入。"""

    from lca.harness.projection import agent_state as agent_state_module

    src = agent_state_module.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    code_lines = [line for line in body.splitlines() if not line.lstrip().startswith("#")]
    code_body = "\n".join(code_lines)
    assert "state.final_output" not in code_body, (
        "agent_state.py 代码段仍写 state.final_output(ADR-0158 决策 四)"
    )


def test_stop_policy_does_not_read_state_final_output() -> None:
    """stop_policy.py 不含 state.final_output 读取(迁移到 StopDecision.final_output 或 TerminalOutcome)。"""

    # NOTE (round-0344): stop_policy plugin retired by c2b0607eb
    # (stop-decision retirement); termination decisions now live in
    # lca.loop.driver via StopDecision/TerminalOutcome.
    import lca.loop.driver as stop_policy_module

    src = stop_policy_module.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    code_lines = [line for line in body.splitlines() if not line.lstrip().startswith("#")]
    code_body = "\n".join(code_lines)
    assert "state.final_output" not in code_body, "stop_policy.py 代码段仍读 state.final_output"


def _ra029_state(**kwargs):
    from lca.contracts.models.core.policy.budget import create_budget
    from lca.contracts.models.core.state.state import AgentState

    return AgentState(trace_id="t", task="", budget=create_budget(max_steps=10), **kwargs)


def test_turn_of_unbound_single_shot_is_zero() -> None:
    """RA-029: turn_of(None) == 0 -- unbound single-shot has no turn dimension."""
    from lca.contracts.models.core.state.state import turn_of

    assert turn_of(None) == 0


def test_turn_of_reads_typed_field() -> None:
    """RA-029: the typed current_turn field is the single source."""
    from lca.contracts.models.core.state.state import turn_of

    assert turn_of(_ra029_state(current_turn=3)) == 3


def test_turn_of_fails_loud_when_projection_never_ran() -> None:
    """RA-029: a bound state with current_turn=None is a contract violation --
    fail loud instead of silently writing turn=0 journal rows."""
    import pytest

    from lca.contracts.models.core.state.state import turn_of

    state = _ra029_state()
    assert state.current_turn is None
    with pytest.raises(ValueError, match="current_turn"):
        turn_of(state)


def test_current_turn_defaults_to_none_not_zero() -> None:
    """RA-029: the typed field defaults to None (unset), never a silent 0."""
    from lca.contracts.models.core.state.state import AgentState

    assert "current_turn" in AgentState.__annotations__
    assert _ra029_state().current_turn is None
