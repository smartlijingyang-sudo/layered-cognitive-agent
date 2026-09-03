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

    from lca.contracts.models.core.state import AgentState

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

    from lca.plugins.runtime import reducer as reducer_module

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

    from lca.plugins.phase_graph import stop_policy as stop_policy_module

    src = stop_policy_module.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    code_lines = [line for line in body.splitlines() if not line.lstrip().startswith("#")]
    code_body = "\n".join(code_lines)
    assert "state.final_output" not in code_body, "stop_policy.py 代码段仍读 state.final_output"
