"""SkillRouter 默认实现 —— 运行时动态选择 Prompt 模板。"""

from __future__ import annotations

from lca.contracts.harness.memory.events import SkillRouted
from lca.contracts.harness.memory.skill import SkillEventSink
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import SkillRouter


async def _emit_session_routed(
    session_events: SkillEventSink | None, template_id: str, decision_path: str
) -> None:
    """把一次路由决定写为 ``skill.routed.v1`` Session 事实。

    未注入 sink 时为 no-op（cognition 层不硬依赖 SessionStore）。
    时序：在对应 ``emit_skill_router_route`` spine 信封之后调用。
    失败语义：sink append 抛错时向 ``route()`` 调用方传播。
    """
    if session_events is None:
        return
    await session_events.append(
        SkillRouted(template_id=template_id, decision_path=decision_path), actor="system"
    )


class KeywordSkillRouter(SkillRouter):
    """基于关键词匹配的零成本路由。

    按优先级遍历规则，第一个命中的关键词决定返回哪个 template_name。
    无命中时返回 default_template。
    """

    def __init__(
        self,
        rules: dict[str, list[str]],
        default_template: str = "react_prompt",
        session_events: SkillEventSink | None = None,
    ) -> None:
        """
        Args:
            rules: template_name → 关键词列表。
                   例: {"research_prompt": ["研究", "调研", "search"],
                        "writing_prompt": ["写", "撰写", "draft"]}
            default_template: 无命中时的默认模板。
            session_events: 可选 Session 事件 sink；注入时每次成功路由
                   追加一条 ``skill.routed.v1`` 事实，缺省不发。
        """
        self._rules = rules
        self._default = default_template
        self._session_events = session_events

    async def route(self, state: AgentState) -> str:
        # PR-3.2: spine envelope for the skill_router.route execution point.
        from lca.plugins.events.publishers.spine_reflector_cognition import (
            emit_skill_router_route,
        )

        try:
            task_lower = state.task.lower()
            for template_name, keywords in self._rules.items():
                if any(kw.lower() in task_lower for kw in keywords):
                    emit_skill_router_route(
                        state_id=state.trace_id,
                        template=template_name,
                        decision_path="keyword_match",
                        outcome="success",
                    )
                    await _emit_session_routed(self._session_events, template_name, "keyword_match")
                    return template_name
            template = self._default
        except BaseException:
            emit_skill_router_route(
                state_id=state.trace_id,
                template=self._default,
                decision_path="keyword_default",
                outcome="failure",
            )
            raise
        emit_skill_router_route(
            state_id=state.trace_id,
            template=template,
            decision_path="keyword_default",
            outcome="success",
        )
        await _emit_session_routed(self._session_events, template, "keyword_default")
        return template


class StaticSkillRouter(SkillRouter):
    """始终返回固定模板，用于测试或不需要动态切换的场景。"""

    def __init__(self, template_name: str, session_events: SkillEventSink | None = None) -> None:
        """
        Args:
            template_name: 固定返回的模板名。
            session_events: 可选 Session 事件 sink；注入时每次路由
                   追加一条 ``skill.routed.v1`` 事实，缺省不发。
        """
        self._template = template_name
        self._session_events = session_events

    async def route(self, state: AgentState) -> str:
        # PR-3.2: spine envelope for the skill_router.route execution point.
        from lca.plugins.events.publishers.spine_reflector_cognition import (
            emit_skill_router_route,
        )

        template = self._template
        emit_skill_router_route(
            state_id=state.trace_id,
            template=template,
            decision_path="static",
            outcome="success",
        )
        await _emit_session_routed(self._session_events, template, "static")
        return template
