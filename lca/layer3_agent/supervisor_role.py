"""Supervisor 角色能力绑定 —— 组合期一次性施加，不是类型区分。

supervisor 是角色而非类型：同一个 SimpleAgent 被放入
OrchestrationContext.supervisor 即承担 supervisor 职责。
本模块把原来散落在 TeamOrchestrator._bind_supervisor 里的
四项绑定逻辑收敛成一个值对象 + 一个纯函数，
使"agent 变成 supervisor"这件事可读、可测、可复用。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.enums import HookEvent
from lca.contracts.protocols import AgentTransport
from lca.contracts.protocols.capabilities import (
    ExposesComponents,
    HookRegistryHolder,
    RosterAware,
    TransportBindable,
)
from lca.contracts.protocols.cognition import CompletionPolicy, SupportsCompletionGuard
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.layer1_cognitive.team_progress.progress_hooks import (
    ledger_tracking_hook,
    progress_injection_hook,
)
from lca.layer3_agent.simple_agent import SimpleAgent


@dataclass(frozen=True)
class SupervisionCapabilities:
    """Supervisor 专属能力清单 —— 值对象。

    把 _bind_supervisor 的四项绑定收敛成显式、可独立测试的参数：
    - transport: 团队通信信道（handoff / delegation 路由）
    - roster_desc: 团队花名册描述（注入 supervisor 的 prompt 上下文）
    - ledger: 委派账本（跟踪成员任务完成状态）
    - completion_policy: 确定性收尾策略（roster coverage 判定）
    """

    transport: AgentTransport | None = None
    roster_desc: str = ""
    ledger: DelegationLedgerProtocol | None = None
    completion_policy: CompletionPolicy | None = None


def apply_supervision(agent: SimpleAgent, caps: SupervisionCapabilities) -> None:
    """在组合期把 SupervisionCapabilities 一次性绑定到 agent 上。

    这是唯一一处"agent 变成 supervisor"的代码位置。
    原地修改 agent.runtime 的组件，不复制 runtime。
    """
    rt = agent.runtime
    if not isinstance(rt, ExposesComponents):
        return

    # transport + roster
    if caps.transport is not None and isinstance(rt.body, TransportBindable):
        rt.body.bind_transport(caps.transport)
    if caps.roster_desc and isinstance(rt.brain, RosterAware):
        rt.brain.set_team_roster(caps.roster_desc)

    # ledger tracking + progress injection hooks
    if caps.ledger is not None and isinstance(rt, HookRegistryHolder):
        rt.hooks.register(HookEvent.POST_ACT, ledger_tracking_hook)
        rt.hooks.register(HookEvent.PRE_THINK, progress_injection_hook)

    # completion guard
    if caps.completion_policy is not None and isinstance(rt, SupportsCompletionGuard):
        rt.install_completion_guard(caps.completion_policy)
