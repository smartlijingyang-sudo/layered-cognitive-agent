"""``{home}/plan.yaml`` 的冻结 schema（ADR-0242 D10 / PR-7）。

plan.yaml 只声明**覆盖**，不复制整个 plan：

- ``prompt.template`` —— 从既有模板注册表选择（缺省继承 profile 默认）；
- ``prompt.sections`` —— 复用既有 section 注册表；``content`` 是对该
  section 渲染结果的**数据覆盖**，不是新 section 类型（I-B11）；
- ``graph.subgraphs`` —— phase 名 → 已登记 bundle 路径，替换该 phase 的
  子图组合。

本模块只校验**形状**（未知字段 fail-closed、frozen 不可变）。模板 / section
/ bundle 的「已登记」校验发生在持有注册表的层（compile 层），不放在
contracts 内 —— contracts 不得 import 插件实现（AGENTS.md §4）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SectionOverride(BaseModel):
    """对既有注册 section 的渲染内容覆盖。

    ``name`` 必须是已登记 section 名（compile 层校验）；``content`` 为
    None 表示不覆盖内容（仅声明该 section 出现在模板中）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    content: str | None = None


class PromptOverride(BaseModel):
    """prompt 模板与 section 覆盖。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template: str | None = None
    sections: tuple[SectionOverride, ...] = ()


class GraphOverride(BaseModel):
    """phase 子图 bundle 覆盖：phase 名 → bundle 路径。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subgraphs: dict[str, str] = Field(default_factory=dict)


class PlanOverlay(BaseModel):
    """``{home}/plan.yaml`` 的完整覆盖声明（ADR-0242 D10）。

    全部字段可选；空 overlay（``prompt: {}`` / ``graph: {}``）= 继承
    profile 默认 plan/prompt，行为与无 assistant 路径一致（I-B8）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: PromptOverride = Field(default_factory=PromptOverride)
    graph: GraphOverride = Field(default_factory=GraphOverride)


__all__ = [
    "GraphOverride",
    "PlanOverlay",
    "PromptOverride",
    "SectionOverride",
]
