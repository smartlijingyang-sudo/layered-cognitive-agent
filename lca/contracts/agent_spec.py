"""声明式构造契约 —— AgentSpec / LeadSpec / TeamSpec（ADR-0033 / ADR-0034）。

AgentSpec 是 Agent 构造的唯一声明式输入：RoleProfile（身份画像）+ 资源
（LLM / 工具）+ 预算 + 组件选择。它作为不可变值对象贯穿门面层与组合根：
Team 组合期从 spec 重建成员对象图，组合无损且可重复，组合根不再从
已封闭的成品图上反向挖掘零件。

TeamSpec 是 Team 构造的唯一声明式输入（ADR-0034）：成员 specs + 治理方式
（``Governance = LeadSpec | Coordination``）。团队形态只由这一个槽位表达——
有主导者与无主导者互斥，非法组合在类型层面不可表示，组合根不再做 XOR
核对。其余一切（策略键、gate、team_awareness）从 governance 单向派生。

组件选择字段支持「注册名字符串 | 实例」双模：字符串经 ComponentRegistry
解析（可插拔），实例直接采用（显式注入）。常量 *_CHOICE_* 是框架内置
注册名，与 layer4_app/defaults.py 的注册键同源，禁止在别处裸写。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.contracts.budget import DEFAULT_MAX_STEPS, DEFAULT_MAX_WALL_CLOCK_SECONDS
from lca.contracts.enums import MemoryLayer
from lca.contracts.role_team import RoleProfile
from lca.contracts.team_coordination import (
    STRATEGY_KEY_LEAD,
    Coordination,
    LeadMandate,
    strategy_key_for_coordination,
)

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

DEFAULT_DELEGATE_MAX_ATTEMPTS = 3
"""Lead 委派同一成员的最大重试次数（lead 路径唯一默认值，禁止别处另立）。"""


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

    LeadMandate 是 lead 的唯一用户旋钮；DecisionGate / 咨询义务（ConsultDuty）
    等组合细节由组合根按 mandate 展开（ADR-0030 / ADR-0035），不出现在本规格中。
    """

    agent: AgentSpec
    mandate: LeadMandate


Governance = LeadSpec | Coordination
"""团队治理方式 —— 谁来决定下一步（ADR-0034）。

两种形态恰居其一，由类型槽位表达，非法组合不可表示：

- ``LeadSpec``：协调者是一个 agent（lead 裁决委派/咨询/自答）。
- ``Coordination``：协调者是一条规则（Pipeline / FanOut / …）。

Lead 因此不是特殊机制，只是治理方式之一——与无主导者路径走同一条
「注册表 → 策略工厂 → 封闭策略」的组合路线。
"""


@dataclass(frozen=True)
class TeamSpec:
    """Team 声明式构造规格 —— 团队组合根的唯一声明式输入（ADR-0034）。

    团队形态的唯一事实来源：成员 + 治理方式。组合根把它编译成封闭的
    ``TeamStrategy``；运行期不再回读本规格之外的任何"团队形态"信号。

    - ``shared_memory_layers``：跨成员共享的记忆层（组合期布线，不进运行期上下文）。
    - ``delegate_max_attempts``：lead 路径的委派重试上限（coordination 路径不适用）。
    - ``observability``：团队级共享观测覆盖（None 时按成员 spec 优先级协商）。
    """

    members: tuple[AgentSpec, ...]
    governance: Governance
    shared_memory_layers: tuple[MemoryLayer, ...] = ()
    delegate_max_attempts: int = DEFAULT_DELEGATE_MAX_ATTEMPTS
    observability: str | Observability | None = None


def strategy_key_for_governance(governance: Governance) -> str:
    """Governance → 策略注册键的唯一派生入口（ADR-0034）。

    组合期派生一次，用于注册表分发与遥测标签；运行期不流转。
    """
    if isinstance(governance, LeadSpec):
        return STRATEGY_KEY_LEAD
    return strategy_key_for_coordination(governance)
