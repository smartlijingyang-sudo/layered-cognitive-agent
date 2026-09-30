"""商用级旗舰多轮对话场景模型 (DTO / Pydantic frozen)。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DialogueTurn(BaseModel):
    """单个对话轮次的测试契约模型。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turn: int
    user: str
    expected_behavior: str
    checklist: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)


class DialogueScenario(BaseModel):
    """单套完整的多轮对话场景用例。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    quadrant: str
    title: str
    description: str = ""
    turns: list[DialogueTurn]


class CommercialEvalSuite(BaseModel):
    """商用评测全量剧本集容器。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = "1.0"
    scenarios: list[DialogueScenario]
