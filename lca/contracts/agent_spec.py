"""声明式构造契约 —— AgentSpec / LeadSpec（ADR-0033）。

AgentSpec 是 Agent 构造的唯一声明式输入：RoleProfile（身份画像）+ 资源
（LLM / 工具）+ 预算 + 组件选择。它作为不可变值对象贯穿门面层与组合根：
Team 组合期从 spec 重建成员对象图，组合无损且可重复，组合根不再从
已封闭的成品图上反向挖掘零件。

组件选择字段支持「注册名字符串 | 实例」双模：字符串经 ComponentRegistry
解析（可插拔），实例直接采用（显式注入）。常量 *_CHOICE_* 是框架内置
注册名，与 layer4_app/defaults.py 的注册键同源，禁止在别处裸写。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.contracts.budget import DEFAULT_MAX_STEPS, DEFAULT_MAX_WALL_CLOCK_SECONDS
from lca.contracts.role_team import RoleProfile
from lca.contracts.team_coordination import LeadMandate

if TYPE_CHECKING:
    from lca.contracts.protocols.cognition import Brain
    from lca.contracts.protocols.infra import LLMAdapter, Observability, StateStore, Tool
    from lca.contracts.protocols.memory import MemorySystem

MEMORY_CHOICE_SIMPLE = "simple"
"""MemorySystem 内置注册名：SimpleMemorySystem。"""

OBSERVABILITY_CHOICE_CONSOLE = "console"
"""Observability 内置注册名：ConsoleObservability。"""

OBSERVABILITY_CHOICE_JSONL_FILE = "jsonl_file"
"""Observability 内置注册名：JSONLFileObservability。"""

STATE_STORE_CHOICE_MEMORY = "memory"
"""StateStore 内置注册名：InMemoryStateStore。"""

BRAIN_CHOICE_DEFAULT = "default"
"""BrainFactory 内置注册名：SimpleBrainFactory。"""


@dataclass(frozen=True)
class AgentSpec:
    """Agent 声明式构造规格 —— 组合根的唯一声明式输入。

    身份在 ``profile``（RoleProfile），其余字段是资源与组件选择。
    frozen 值对象：团队组合期用 ``dataclasses.replace`` 派生变体
    （注入共享观测等），不就地修改。
    """

    profile: RoleProfile
    llm: LLMAdapter
    tools: tuple[Tool, ...] = ()
    max_steps: int = DEFAULT_MAX_STEPS
    max_wall_clock_seconds: int | None = DEFAULT_MAX_WALL_CLOCK_SECONDS
    memory: str | MemorySystem = MEMORY_CHOICE_SIMPLE
    observability: str | Observability = OBSERVABILITY_CHOICE_CONSOLE
    state_store: str | StateStore = STATE_STORE_CHOICE_MEMORY
    brain: str | Brain = BRAIN_CHOICE_DEFAULT


@dataclass(frozen=True)
class LeadSpec:
    """有主导者团队的 lead 入口规格：AgentSpec + LeadMandate。

    LeadMandate 是 lead 的唯一用户旋钮；DecisionGate / SupervisorReasoner
    等组合细节由组合根按 mandate 展开（ADR-0030），不出现在本规格中。
    """

    agent: AgentSpec
    mandate: LeadMandate
