"""ADR-0158 决策 五:Result.from_state 删除 + Result.output 单一来源(terminal_outcome)。

约束(ADR-0077 §三「Result 只读 TerminalOutcome 与 projection」):

- Result 不再有 from_state(state) 类方法
- Result.output 仅由 TerminalOutcome.final_output_ref 解析得到
- 测试守门:Result 类不暴露 from_state;既有调用方迁移至 TerminalOutcome 读取
"""

from __future__ import annotations

import inspect

from lca.contracts.models.core.result import Result


def test_result_has_no_from_state_classmethod() -> None:
    """ADR-0158 决策 五:Result.from_state 必须删除。"""

    assert not hasattr(Result, "from_state"), (
        "Result.from_state 必须删除(ADR-0158 决策 五);Result.output 改读 "
        "TerminalOutcome.final_output_ref(ADR-0077 §三)。"
    )


def test_result_from_state_not_in_source() -> None:
    """Result 源文件不含 from_state 字符串引用。

    文档引用("已删除" 注释)允许存在,以解释 ADR;但代码定义
    (def from_state)与调用必须清除。
    """

    from lca.contracts.models.core import result as result_module

    src = result_module.__file__ or ""
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    # 只允许在注释里出现 from_state 字面量;代码里必须清除
    code_lines = [
        line
        for line in body.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code_body = "\n".join(code_lines)
    assert "from_state" not in code_body, (
        "result.py 代码段(非注释)仍含 from_state 定义/调用(ADR-0158 决策 五)"
    )


def test_result_output_init_signature() -> None:
    """Result.output 仍可被构造(保留 carrier 字段)。"""

    sig = inspect.signature(Result.__init__)
    assert "output" in sig.parameters, "Result.output 应作为构造字段保留"