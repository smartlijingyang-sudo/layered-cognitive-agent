"""标准人工回复到声明式恢复事实的 adapter。

具体交互渠道的语义停留在这个 seam 内；``CognitiveRuntime`` 只接收已经
规范化的 ``ResumeInput``，并委托唯一的 Reducer 折叠状态。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols.session.resume_input import ResumeInput, ResumeInputAdapter


class HumanAnswerResumeInputAdapter(ResumeInputAdapter):
    """把人工文本回复转换为可审计的 ASK_HUMAN Turn。

    这是默认交互实现，而非运行时规则。其他 carrier 可以实现同一协议，返回
    自己的 ``ResumeInput``，例如批准回执、自动重试令牌或结构化表单答案。
    """

    def normalize(self, input_value: object | None) -> ResumeInput:
        """保留原始输入，并在存在输入时写入对应的人工回复 Turn。"""

        if input_value is None:
            return ResumeInput(input_value=None)
        answer_text = _as_human_answer_text(input_value)
        answer_observation = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=answer_text,
            extra={"source": "human_answer", "tool_name": "askUserQuestion"},
        )
        answer_decision = Decision(
            decision_id=new_id("dec"),
            action_type=ActionType.ASK_HUMAN,
            rationale="Human-in-the-loop answer received.",
            confidence=1.0,
            tool_calls=[
                ToolCall(
                    call_id=new_id("tc"),
                    tool_name="askUserQuestion",
                    arguments={},
                )
            ],
        )
        return ResumeInput(
            input_value=input_value,
            turn=Turn(decision=answer_decision, observation=answer_observation),
        )


def _as_human_answer_text(input_value: object) -> str:
    """Normalize supported user-facing carriers before building a resume fact."""
    if isinstance(input_value, str):
        return input_value
    if isinstance(input_value, AgentMessage):
        return agent_message_as_text(input_value)
    raise ValueError("human answer resume input must be a string or AgentMessage")


__all__ = ["HumanAnswerResumeInputAdapter"]
