"""SkillRouter 默认实现 —— 运行时动态选择 Prompt 模板。"""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import SkillRouter


class KeywordSkillRouter(SkillRouter):
    """基于关键词匹配的零成本路由。

    按优先级遍历规则，第一个命中的关键词决定返回哪个 template_name。
    无命中时返回 default_template。
    """

    def __init__(
        self,
        rules: dict[str, list[str]],
        default_template: str = "react_prompt",
    ) -> None:
        """
        Args:
            rules: template_name → 关键词列表。
                   例: {"research_prompt": ["研究", "调研", "search"],
                        "writing_prompt": ["写", "撰写", "draft"]}
            default_template: 无命中时的默认模板。
        """
        self._rules = rules
        self._default = default_template

    async def route(self, state: AgentState) -> str:
        task_lower = state.task.lower()
        for template_name, keywords in self._rules.items():
            if any(kw.lower() in task_lower for kw in keywords):
                return template_name
        return self._default


class StaticSkillRouter(SkillRouter):
    """始终返回固定模板，用于测试或不需要动态切换的场景。"""

    def __init__(self, template_name: str) -> None:
        self._template = template_name

    async def route(self, state: AgentState) -> str:
        return self._template
