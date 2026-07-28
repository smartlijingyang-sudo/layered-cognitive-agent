"""ScenarioLLM —— 用于团队级端到端测试的场景化确定性 LLM。

与 lca.layer0_infra.llm_adapter.mock_llm.MockLLMAdapter 的区别：
MockLLMAdapter 只认识"纯算术题"这一种模式，无法驱动
delegate / handoff / debate 等真实多角色协作场景。

ScenarioLLM 按 ROLE 与 CONTEXT 中的 TOOL_RESULT 前缀做路由，
模拟一个真实业务团队（跨境电商新品上市评估）在
Supervisor 委派 / 流水线 / 并行 / 辩论 / 分诊移交 / DAG 编排
六种组织形态下应产生的决策序列。

所有分支都是"读 prompt -> 吐 JSON StructuredDecision"的纯函数式路由，
不依赖隐藏的进程内状态（唯一例外见 SupervisorLLM 类文档字符串），
这样每一步决策都可以从打印出的 prompt/response 日志中被复现和调试。
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.protocols import LLMAdapter

# ---------------------------------------------------------------------------
# 场景常量：跨境电商新品上市评估团队
# ---------------------------------------------------------------------------

COST_PRICE_USD = 26
MARKUP = 1.8


def _extract(prompt: str, field: str) -> str:
    m = re.search(rf"{field}:\s*([^\n]+)", prompt)
    return m.group(1).strip() if m else ""


def _extract_tool_result(prompt: str) -> str | None:
    """从 CONTEXT 区块里找最近一次 TOOL_RESULT（working memory 只保留最后一条）。"""
    m = re.search(r"TOOL_RESULT:\s*([^\n]+)", prompt)
    return m.group(1).strip() if m else None


def _decision(**kwargs: Any) -> str:
    return json.dumps(kwargs, ensure_ascii=False)


class ScenarioLLM(LLMAdapter):
    """路由到各角色决策逻辑的场景化 Mock LLM。"""

    name = "scenario-mock-llm"

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        role = _extract(prompt, "ROLE")
        task = _extract(prompt, "USER_TASK")
        tool_result = _extract_tool_result(prompt)
        is_supervisor = "你是团队 Supervisor" in prompt

        if is_supervisor:
            return self._supervisor(task, tool_result)
        if "市场分析" in role:
            return self._market_analyst(task)
        if "定价" in role:
            return self._pricing_specialist(task, tool_result)
        if "文案" in role:
            return self._copywriter(role, task)
        if "风控" in role or "风险" in role:
            return self._risk_reviewer(task)
        if "退款" in role:
            return self._refund_specialist(task)
        if "技术支持" in role:
            return self._tech_support(task)
        return _decision(
            action_type="respond",
            response_text=f"[{role}] 未定义场景分支，兜底直接作答：{task}",
            rationale="fallback",
            confidence=0.3,
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        text = await self.complete(prompt, **kwargs)
        for ch in text:
            yield ch

    # -- Supervisor：单向委派链 -------------------------------------------
    def _supervisor(self, task: str, tool_result: str | None) -> str:
        """Supervisor 的决策只读当前 prompt（含最近一条 TOOL_RESULT）。

        注意：SimpleMemorySystem.working 层每步都会被覆盖为最新一条记录，
        所以 Supervisor 在第 N 步只能看到"上一步"的结果，看不到更早的委派
        结果 —— 这是框架当前的真实行为，不是本 mock 的简化。测试里会专门
        断言这一点（见 finding #1）。
        """
        if tool_result is None:
            return _decision(
                action_type="delegate",
                target_role="市场分析师",
                subtask=f"评估以下新品在目标市场的销售潜力：{task}",
                rationale="任务开始，第一步委派市场分析师评估市场潜力",
                confidence=0.9,
            )
        if "MARKET_ANALYSIS" in tool_result:
            return _decision(
                action_type="delegate",
                target_role="定价专员",
                subtask=f"成本价 {COST_PRICE_USD} 美元，请给出建议零售定价",
                rationale="市场分析已完成，委派定价专员计算建议零售价",
                confidence=0.9,
            )
        if "PRICE_RECOMMENDATION" in tool_result:
            return _decision(
                action_type="delegate",
                target_role="文案撰写",
                subtask=f"结合定价信息撰写新品上市文案。{tool_result}",
                rationale="定价已完成，委派文案撰写团队产出上市文案",
                confidence=0.9,
            )
        if "LAUNCH_COPY" in tool_result:
            return _decision(
                action_type="respond",
                response_text=f"新品上市评估已完成。最终交付物：{tool_result}",
                rationale="全部子任务完成，向用户汇总答复",
                confidence=0.95,
            )
        return _decision(
            action_type="respond",
            response_text=f"任务完成，最近结果：{tool_result}",
            rationale="兜底收尾",
            confidence=0.5,
        )

    # -- 团队成员 -----------------------------------------------------------
    def _market_analyst(self, task: str) -> str:
        return _decision(
            action_type="respond",
            response_text=(
                "MARKET_ANALYSIS: 东南亚市场对无线降噪耳机需求增长明显，"
                "预测首月可售出约1200件，建议进入；主要风险为物流时效与本地认证周期。"
            ),
            rationale=f"基于任务「{task}」完成市场判断，无需调用工具",
            confidence=0.85,
        )

    def _pricing_specialist(self, task: str, tool_result: str | None) -> str:
        if tool_result is None:
            return _decision(
                action_type="use_tool",
                tool_name="calculator",
                arguments={"expression": f"{COST_PRICE_USD}*{MARKUP}"},
                rationale=f"任务要求基于成本价核算定价（{task}），调用计算器求精确值",
                confidence=0.9,
            )
        return _decision(
            action_type="respond",
            response_text=f"PRICE_RECOMMENDATION: 建议零售价 ${tool_result} 美元（成本 * {MARKUP} 倍加价）",
            rationale="已拿到计算器精确结果，直接作答",
            confidence=0.95,
        )

    def _copywriter(self, role: str, task: str) -> str:
        variants = {
            "A": "「静界降噪，出行必备」——专属发售价早鸟立减，抢先体验。",
            "B": "「戴上即安静」——东南亚首发，48小时闪送到家。",
            "C": "「降噪不将就」——工程师调校，专为通勤党打造。",
        }
        suffix = role.strip()[-1] if role.strip()[-1] in variants else "A"
        return _decision(
            action_type="respond",
            response_text=f"LAUNCH_COPY: {variants[suffix]}",
            rationale=f"依据任务上下文「{task[:20]}...」产出候选文案",
            confidence=0.8,
        )

    def _risk_reviewer(self, task: str) -> str:
        return _decision(
            action_type="respond",
            response_text="RISK_REVIEW: 合规风险低，需关注东南亚本地认证周期（约3-4周）。",
            rationale=f"针对「{task[:20]}...」完成风险复核",
            confidence=0.8,
        )

    def _refund_specialist(self, task: str) -> str:
        return _decision(
            action_type="use_tool",
            tool_name="refund_system",
            arguments={"case": task},
            rationale="尝试通过退款系统处理，但该工具未在此 Agent 的权限清单中注册",
            confidence=0.4,
        )

    def _tech_support(self, task: str) -> str:
        return _decision(
            action_type="respond",
            response_text=(
                "已排查：连接失败为蓝牙配对缓存问题，指导用户清除配对记录并重新配对，"
                "问题已解决，无需退款。"
            ),
            rationale=f"技术支持基于「{task[:20]}...」给出解决方案",
            confidence=0.9,
        )


class DebatePricingLLM(LLMAdapter):
    """辩论场景：两位定价策略师首轮观点冲突，第二轮收敛。"""

    name = "debate-pricing-mock-llm"

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        role = _extract(prompt, "ROLE")
        converging = "Previous proposals" in prompt
        if not converging:
            price = 39.9 if "保守" in role else 59.9
            stance = "保守定价，优先走量" if "保守" in role else "激进定价，优先毛利"
            return _decision(
                action_type="respond",
                response_text=f"PROPOSAL: ${price}（{stance}）",
                rationale=stance,
                confidence=0.7,
            )
        return _decision(
            action_type="respond",
            response_text="PROPOSAL: $49.9（综合双方意见后的折衷定价）",
            rationale="参考上一轮对方提案，收敛到折衷价格",
            confidence=0.9,
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        text = await self.complete(prompt, **kwargs)
        for ch in text:
            yield ch


def _extract_proposal_price(text: str | None) -> float | None:
    m = re.search(r"PROPOSAL:\s*\$([\d.]+)", text or "")
    return float(m.group(1)) if m else None


class PriceConflictMonitor:
    """真正"会干活"的 ConflictMonitor：价格分歧超过阈值才判定为冲突。

    对照组：defaults.py 里给 'debate' 注册的 SimpleConflictMonitor.check()
    永远返回 []，导致 DebateStrategy 第一轮就短路收敛。这个类证明只要
    接入一个真正检测分歧的实现，DebateStrategy 本身的多轮收敛机制是可以
    正常工作的——问题出在默认注册的 stub 实现，不在 DebateStrategy 本身。
    """

    async def check(self, state: Any, candidates: list[Any]) -> list[str]:
        prices = [
            p for c in candidates if (p := _extract_proposal_price(c.response_text)) is not None
        ]
        if len(prices) < 2:
            return []
        if max(prices) - min(prices) > 5.0:
            return ["price_disagreement"]
        return []
