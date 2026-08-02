# ADR-0024: Registries 值对象取代三个进程级全局单例

**状态**：Proposed
**Relates-to**：ADR-0005、ADR-0018、ADR-0023（§5）
**Supersedes**：`docs/registry-catalog.md` 中"发现型注册表生命周期 = 全局单例"的表述；ADR-0023 §5 中"保留 `get_global_brain_factory_registry()` 单例访问器"的决定

---

## 摘要

`ComponentRegistry`、`NamedRegistry[BrainFactory]`、`TeamProcessStrategyRegistry` 目前各有一个进程级全局单例（`get_global_registry()` / `get_global_brain_factory_registry()` / `get_global_orchestration_registry()`），外加一个幂等标记 `_defaults_registered`。`TeamOrchestrator`（L3）直接调用这些全局访问函数来拿协作方，这既违反了 `docs/registry-catalog.md` 自己写的硬不变量，也违反了 `AGENTS.md` "同层模块间不直接 import，通过依赖注入获取协作方"的规则。

本 ADR 用一个显式的、不可变的 `Registries` 值对象取代这三个全局单例，构造下沉到组合根 `layer4_app`。三个 `get_global_*()` 函数、对应的模块级可变字典、以及幂等标记，在同一次改动里**直接删除**，不保留兼容访问器。`TeamOrchestrator.__init__` 新增的 `registries` 参数是**必填**关键字参数，没有隐藏回落路径。全仓库真实调用方——业务代码、示例、9 个测试文件——在同一次改动里一起更新完毕。改动完成后，全仓库不再有任何 `get_global_*` 函数；唯一还存在的进程级可变状态是 `api.py` 里一个封装良好、可显式绕开的懒加载 `Assembly` 单例，用来保留 `Agent(...)` 三行上手体验（ADR-0005）。

---

## 1. 背景

`docs/registry-catalog.md` 写着这样一条硬不变量：

> 3. 业务层（L0–L3）不要调用 `get_global_*` 组装对象图；只允许 L4 / 编排策略的默认工厂解析。

但 `lca/layer3_agent/team_orchestrator.py`（L3）自己违反了这条规则。它的 import 是：

```python
from lca.layer0_infra.component_registry import get_global_registry
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
```

并在 `__init__` 里直接调用 `get_global_orchestration_registry()` 一次（解析 process 策略）、`get_global_registry()` 两次（`_create_member_status` 解析 `member_status`，`_resolve_decision_gate` 解析 `decision_gate`）。也就是说文档写的规则，L3 自己没有遵守——这不是风格偏好，是一条已经写进项目文档、但被代码本身违反的硬约束。

`AGENTS.md` 里另一条设计约束说得更直接：

> 同层模块间不直接 import，通过依赖注入（构造函数参数）获取协作方

`TeamOrchestrator` 靠模块级函数拿协作方（三个注册表），正是"不通过构造函数参数获取协作方"的反面例子。这次重构把 `TeamOrchestrator` 拉回项目自己写好的规则里，不是引入新哲学。

真实的牵扯面（grep 全仓库得到，按调用点，不含各注册表自身的定义处）：

| 全局访问函数 / 状态 | 定义位置 | 真实调用点 |
|---|---|---|
| `get_global_registry()` | `layer0_infra/component_registry.py` | `layer4_app/assembly.py`（1 处）、`layer4_app/defaults.py`（1 处）、`layer3_agent/team_orchestrator.py`（2 处）、`examples/pluggability_demo/pluggability_demo.py`（2 处） |
| `defaults_registered()` / `mark_defaults_registered()` | 同上 | 仅 `layer4_app/defaults.py` 内部 |
| `get_global_brain_factory_registry()` | `layer2_runtime/strategy_registry.py` | `layer4_app/assembly.py`（1 处）、`layer2_runtime/__init__.py`（re-export）、`layer4_app/defaults.py`（1 处）、`tests/test_protocol_compliance.py`（1 处） |
| `get_global_orchestration_registry()` | `layer3_agent/orchestration_registry.py` | `layer3_agent/team_orchestrator.py`（1 处）、`layer3_agent/__init__.py`（re-export）、`layer4_app/defaults.py`（1 处）、5 个测试文件：`test_graph_strategy.py`、`test_parallel_strategy.py`、`test_debate_strategy.py`、`test_orchestration_coverage.py`、`test_handoff_strategy.py` |
| `ensure_defaults()` | `layer4_app/defaults.py` | `layer4_app/assembly.py`（`assemble_agent` / `assemble_team` 各一次）、`layer4_app/api.py`（`Agent.__init__` / `MultiAgentTeam.__init__` 各一次）、7 个测试文件模块级副作用调用：`test_debate_strategy_conflict_gap.py`、`test_graph_strategy.py`、`test_parallel_strategy.py`、`test_debate_strategy.py`、`test_orchestration_coverage.py`、`test_step4_supervisor_bind_team.py`、`test_handoff_strategy.py` |

注意最后一行：调用 `ensure_defaults()` 的测试文件（7 个）和直接调用 `get_global_orchestration_registry()` 的测试文件（5 个）**不是同一个集合**——`test_debate_strategy_conflict_gap.py` 只调用了 `ensure_defaults()` 作为构造 `Agent` / `MultiAgentTeam` 前的安全网，从未直接碰注册表。这个区分决定了 §7 中每个测试文件的具体改法不完全相同。

另外，`examples/pluggability_demo/pluggability_demo.py` 里有一处真实（非测试）用例：运行前动态注册自定义实现——

```python
reg = get_global_registry()
reg.register("memory", "logging", LoggingMemorySystem)
...
agent = Agent(..., memory="logging")
```

全局单例删除后，这条路径需要一个等价物（见 §5）。

---

## 2. 决定

**核心决定**：三个全局单例、其访问函数、以及配套的幂等标记，在同一次改动里直接删除，不保留兼容访问器；`registries` 在 `TeamOrchestrator` 里是必填参数，没有隐藏回落。

- **新增 `lca/contracts/registries.py`：`Registries`** —— 一个不带默认值的 frozen dataclass，字段全部是 `contracts` 已有 / 新增的 Protocol。

  刻意不提供默认值：如果要为字段提供开箱即用的默认工厂，就必须在 `contracts` 内部 import 具体实现类（例如 `layer0_infra.component_registry.ComponentRegistry`），而 `pyproject.toml` 里的 import-linter 契约 3（"contracts 纯净性：不得依赖任何具体实现"）明确禁止 `lca.contracts` import `lca.layer0_infra`。因此"给我一份可用的默认 `Registries`"这件事下沉到组合根 `layer4_app`（见 §4.5 的 `build_default_registries()`）。

- **`lca/contracts/mechanisms.py` 新增 `ComponentRegistryProtocol`。**

  `NamedRegistryProtocol.resolve(name)` 是单参数接口，而 `ComponentRegistry` 的真实接口是 `require(category, name)` 两参数——两者结构不兼容，需要一个独立的 Protocol，`Registries.components` 才能有正确的静态类型。

- **`lca/layer0_infra/component_registry.py`**：删除 `_global_registry`、`get_global_registry()`、`_defaults_registered`、`defaults_registered()`、`mark_defaults_registered()`；只留 `RegistryKeyError`、`NamedRegistry`、`ComponentRegistry` 三个纯类。

- **`lca/layer2_runtime/strategy_registry.py`：整个文件删除。** 删掉单例访问器之后，这个模块只剩一层 `NamedRegistry[BrainFactory]` 的类型别名，没有独立存在的理由——直接在需要的地方用 `NamedRegistry[BrainFactory]()`。这与 ADR-0023 §5"溶解 `BrainFactoryRegistry`"的方向一致，这次连访问器也一并溶解。

- **`lca/layer3_agent/orchestration_registry.py`**：保留 `TeamProcessStrategyRegistry` 类（它有真实行为——覆写了 `resolve()` 语义），删除 `_global_orchestration_registry`、`get_global_orchestration_registry()`。

- **`lca/layer3_agent/team_orchestrator.py`**：`__init__` 新增**必填**关键字参数 `registries: Registries`；`_create_member_status` / `_resolve_decision_gate` 从内部摸全局改为接收 `registries` 参数。

- **`lca/layer4_app/defaults.py`**：`register_defaults(registries: Registries) -> None` 参数改为必填；删除 `ensure_defaults()` / `defaults_registered()` / `mark_defaults_registered()`；新增 `build_default_registries() -> Registries`（构造一份全新的、已注册内置默认实现的 `Registries`——这是"给我一份开箱即用默认配置"的唯一入口）。

- **`lca/layer4_app/assembly.py`**：新增 `Assembly` 类，唯一持有 `Registries` 实例的地方；`assemble_agent` / `assemble_team` 从模块级函数改为 `Assembly` 的方法（方法名不变，与 `tests/test_refactor_guards.py` 的字符串断言兼容）；新增 `register_component` / `register_brain_factory` / `register_orchestration_strategy` 三个方法。

  新增这三个方法的直接原因：`examples/pluggability_demo/pluggability_demo.py` 有一处真实用例，在运行前动态注册自定义实现（`get_global_registry()` 后 `reg.register("memory", "logging", ...)`，再构造 `Agent(memory="logging")`）。全局单例删除后，这条路径需要等价物（见 §5）。

- **`lca/layer4_app/api.py`**：`Agent` / `MultiAgentTeam` 新增可选 `assembly: Assembly | None` 参数；模块级保留**唯一**一处懒加载单例 `_default_assembly`，供 `from lca import Agent; Agent(...)` 三行体验（ADR-0005）不变。

删除之后，全仓库不再有任何 `get_global_*` 函数，也不再有任何独立于对象之外的模块级可变字典 / 标记。唯一还活着的进程级状态是 `api.py` 里那一个 `_default_assembly`——从"三个分散的可变全局 + 一个幂等标记"收敛成"一个封装良好、可被显式绕开的单例"。

---

## 3. contracts 层新增类型

### 3.1 `lca/contracts/mechanisms.py`

在文件末尾（`NamedRegistryProtocol` 之后）追加：

```python
@runtime_checkable
class ComponentRegistryProtocol(Protocol):
    """按 (category, name) 注册和解析组件实现的通用接口。

    与 NamedRegistryProtocol 的区别：键是二元组 (category, name)，
    对应发现型组件（memory / observability / state_store / decision_gate 等）
    按类别分组管理的场景。具体实现（如 ComponentRegistry）在 layer0 提供。
    """

    def register(self, category: str, name: str, impl: Any) -> None: ...
    def get(self, category: str, name: str) -> Any | None: ...
    def require(self, category: str, name: str) -> Any: ...
    def list(self, category: str) -> list[str]: ...
```

不需要新增 import——文件顶部已有 `from typing import Any, Protocol, runtime_checkable`。

同时更新模块顶部的边界判定说明，把新 Protocol 纳入既有的分类描述：

```python
# 旧
- NamedRegistryProtocol / TransportRegistryProtocol：按名解析实现，无业务规则

# 新
- NamedRegistryProtocol / ComponentRegistryProtocol / TransportRegistryProtocol：按名解析实现，无业务规则
```

### 3.2 `lca/contracts/registries.py`（新文件）

```python
"""组合期注册表包 —— 用显式值对象替代进程级全局单例（ADR-0024）。

Registries 是一次组合过程（一个 Assembly 实例）共享的全部可插拔组件注册表。
字段类型全部是 contracts 已有的 Protocol，不引用任何具体实现类，
因此可以被 L0-L4 任意层安全导入而不违反 import-linter 的单向依赖契约。

刻意不提供默认值：拿到"一份可用的具体注册表实例"是组合根
（layer4_app）的职责，不是 contracts 的职责——contracts 只声明形状。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.mechanisms import ComponentRegistryProtocol, NamedRegistryProtocol


@dataclass(frozen=True)
class Registries:
    """一次组合过程共享的三个发现型注册表。"""

    components: ComponentRegistryProtocol
    brain_factories: NamedRegistryProtocol
    orchestration: NamedRegistryProtocol
```

`@dataclass(frozen=True)`、零自定义方法——直接满足 `tests/test_contracts_purity.py`（ADR-0015）对 `contracts/` 目录的约束（该测试对每个非 Protocol / 非异常 / 非枚举类要求 `@dataclass` 装饰器，并逐个检查非 dunder 方法是否在 `_GRANDFATHERED_METHODS` 白名单中），不需要加进白名单表。`frozen=True` 是有意为之：`Registries` 本身（三个字段的绑定关系）组装完就不应该再变，"注册新实现"这个动作发生在字段指向的注册表对象内部（`registries.components.register(...)`），不是替换字段本身。

### 3.3 `lca/contracts/protocols/__init__.py`

在 `from lca.contracts.mechanisms import (...)` 块中加入 `ComponentRegistryProtocol`（按现有的字母序排列，插在 `EventBus` 之前）：

```python
# 旧
from lca.contracts.mechanisms import (
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
)

# 新
from lca.contracts.mechanisms import (
    ComponentRegistryProtocol,
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
)
```

`__all__` 列表同样按字母序插入（在 `"CandidateEvaluationPipeline"` 和 `"Critic"` 之间）：

```python
("CandidateEvaluationPipeline",)
("ComponentRegistryProtocol",)
("Critic",)
```

### 3.4 `lca/contracts/__init__.py`

新增一条模块导入（按现有的按模块名字母序排列，插在 `from lca.contracts.protocols import ...` 和 `from lca.contracts.result import ...` 之间）：

```python
from lca.contracts.registries import Registries
```

`from lca.contracts.mechanisms import (...)` 块同样加入 `ComponentRegistryProtocol`：

```python
# 旧
from lca.contracts.mechanisms import (
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
)

# 新
from lca.contracts.mechanisms import (
    ComponentRegistryProtocol,
    EventBus,
    Hook,
    HookRegistry,
    NamedRegistryProtocol,
)
```

`__all__` 按字母序插入两处：`"ComponentRegistryProtocol"` 在 `"CacheConfig"` 和 `"Decision"` 之间；`"Registries"` 在 `"Reflection"` 和 `"Result"` 之间：

```python
("CacheConfig",)
("ComponentRegistryProtocol",)
("Decision",)
...
("Reflection",)
("Registries",)
("Result",)
```

---

## 4. 各文件最终版本

以下每个文件给出完整最终内容，可直接落地，无需对照当前仓库版本。

### 4.1 `lca/layer0_infra/component_registry.py`

```python
"""注册表基础设施 —— ComponentRegistry + NamedRegistry 泛型基类。

语义约定（PR-5 / ADR-0019）：
- ``get``：软查询，找不到返回 None
- ``require`` / ``NamedRegistry.resolve``：硬查询，找不到 raise RegistryKeyError

ADR-0024：本模块不再持有进程级全局单例。ComponentRegistry / NamedRegistry
的实例生命周期由调用方决定 —— 框架默认路径中，实例归 Assembly 私有持有
（见 lca.contracts.registries.Registries、lca.layer4_app.assembly.Assembly）。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from lca.contracts.mechanisms import NamedRegistryProtocol

_T = TypeVar("_T")
_StrList = list[str]  # 避免类内方法名 list 遮蔽内置 list 类型


class RegistryKeyError(ValueError):
    """按名称查找注册表条目失败。

    继承 ValueError 以保持向后兼容（已有测试 assertRaises(ValueError)）。
    """

    def __init__(self, key: str, registry_kind: str, available: list[str]) -> None:
        self.key = key
        self.registry_kind = registry_kind
        self.available = available
        super().__init__(f"未注册{registry_kind} {key!r}，可用: {available}")


class NamedRegistry(NamedRegistryProtocol, Generic[_T]):
    """按名称注册和解析实体的泛型基类。

    子类通过 ``_REGISTRY_KIND`` 声明种类名（用于错误消息），
    可选择覆盖 ``resolve()`` 以改变解析语义（如工厂调用、类型转换）。
    """

    _REGISTRY_KIND: str = "条目"

    def __init__(self) -> None:
        self._entries: dict[str, _T] = {}

    def register(self, name: str, impl: _T) -> None:
        self._entries[name] = impl

    def get(self, name: str) -> _T | None:
        """软查询：找不到返回 None。"""
        return self._entries.get(name)

    def resolve(self, name: str) -> _T:
        impl = self._entries.get(name)
        if impl is None:
            raise RegistryKeyError(name, self._REGISTRY_KIND, self.list())
        return impl

    def list(self) -> _StrList:
        return list(self._entries.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._entries


class ComponentRegistry:
    """按 (category, name) 注册和解析组件实现（发现型注册表）。

    category 例如 "observability"、"memory"、"state_store" 等；
    name 是用户可见的实现名称，例如 "console"、"simple" 等。
    值可以是类（无参构造）或工厂函数（接受上下文参数）。

    运行时绑定型注册表（Action / Tool / Transport）应由 Assembly 注入实例，
    不要用 ComponentRegistry 承载。
    """

    def __init__(self) -> None:
        self._registries: dict[str, dict[str, Any]] = {}

    def register(self, category: str, name: str, impl: Any) -> None:
        self._registries.setdefault(category, {})[name] = impl

    def get(self, category: str, name: str) -> Any | None:
        """软查询：找不到返回 None。"""
        return self._registries.get(category, {}).get(name)

    def require(self, category: str, name: str) -> Any:
        """硬查询：找不到 raise RegistryKeyError。"""
        impl = self.get(category, name)
        if impl is None:
            raise RegistryKeyError(name, category, self.list(category))
        return impl

    def list(self, category: str) -> _StrList:
        return list(self._registries.get(category, {}).keys())

    def list_categories(self) -> _StrList:
        return sorted(self._registries.keys())

    def get_registry(self, category: str) -> dict[str, Any]:
        return self._registries.get(category, {})
```

相对当前版本，删除文件末尾的五行/函数：`_global_registry = ComponentRegistry()`、`_defaults_registered = False`、`get_global_registry()`、`defaults_registered()`、`mark_defaults_registered()`。`ComponentRegistry` 类体本身不变，仅类文档字符串把"应由 AgentAssembly 注入实例，不要用全局 ComponentRegistry 承载"改为"应由 Assembly 注入实例，不要用 ComponentRegistry 承载"（`Assembly` 现在是 §4.6 新增的真实类名，不再是占位性的措辞）。

### 4.2 `lca/layer2_runtime/strategy_registry.py` —— 整个文件删除

当前内容（`_global_brain_registry` + `get_global_brain_factory_registry()`）全部删除。`NamedRegistry[BrainFactory]` 直接在 `lca/layer4_app/defaults.py::build_default_registries()` 里构造（见 §4.5），不再需要独立模块。

同步修改 `lca/layer2_runtime/__init__.py`：

```python
"""L2 认知运行时层 —— 核心 Loop + StopRule。"""

from lca.layer2_runtime.default_loop_judge import DefaultStopRule
from lca.layer2_runtime.event_emission import make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime

__all__ = [
    "CognitiveRuntime",
    "DefaultStopOutcomePolicy",
    "DefaultStopRule",
    "make_event_emitting_hook",
]
```

（相对当前版本：删除 `from lca.layer2_runtime.strategy_registry import get_global_brain_factory_registry` 这一行 import，以及 `__all__` 里的 `"get_global_brain_factory_registry"` 条目。）

### 4.3 `lca/layer3_agent/orchestration_registry.py`

```python
"""TeamProcessStrategyRegistry —— 按 process 名称注册和解析编排策略。

L3 层职责：
    注册表模式（Registry Pattern）的实现。
    将编排策略名称（如 "hierarchical"、"sequential"）映射到
    TeamProcessStrategy 实例，消除 TeamOrchestrator 中的 if/elif 分发。
    工厂签名 ``() -> TeamProcessStrategy``，resolve 时自动调用工厂。

ADR-0024：不再提供全局单例；实例归 Registries.orchestration 持有，
由调用方（通常是 Assembly）显式构造和传递。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.protocols import TeamProcessStrategy
from lca.layer0_infra.component_registry import NamedRegistry

OrchestrationFactory = Callable[[], TeamProcessStrategy]


class TeamProcessStrategyRegistry(NamedRegistry[OrchestrationFactory]):
    """按名称注册和查找 TeamProcessStrategy 工厂。

    工厂签名: ``() -> TeamProcessStrategy``
    策略实例在 ``run()`` 时通过 TeamContext 获取运行时数据。

    ``resolve()`` 有意覆盖基类签名：基类返回工厂（``OrchestrationFactory``），
    本类调用工厂后返回策略实例（``TeamProcessStrategy``），
    这是注册表模式的常见变体——注册的是工厂，消费方拿到的是产品。
    """

    _REGISTRY_KIND = "编排策略"

    def resolve(self, name: str) -> TeamProcessStrategy:  # type: ignore[override]
        # 有意将返回类型从 OrchestrationFactory 变为 TeamProcessStrategy 实例：
        # 注册表存工厂，resolve 调用工厂返回产品，消费方无需知道工厂细节。
        factory = super().resolve(name)
        return factory()

    def list_strategies(self) -> list[str]:
        return self.list()

    def has(self, name: str) -> bool:
        return name in self
```

相对当前版本，删除文件末尾的 `_global_orchestration_registry: TeamProcessStrategyRegistry | None = None` 模块级变量和 `get_global_orchestration_registry()` 函数；`TeamProcessStrategyRegistry` 类体本身不变。

同步修改 `lca/layer3_agent/__init__.py`：

```python
"""L3 Agent 抽象层 —— 单 Agent 封装 + 团队编排。

L3 层职责：
    将 L2 的 CognitiveRuntime 封装为 CognitiveAgent（单 Agent 执行单元），
    并通过 TeamOrchestrator + TeamProcessStrategy 实现多 Agent 编排。
    支持六种编排模式：hierarchical / sequential / parallel / handoff / debate / graph。
    所有策略通过注册表解析，L3 不含 if/elif 业务分发。
"""

from lca.layer3_agent.orchestration_registry import TeamProcessStrategyRegistry
from lca.layer3_agent.simple_agent import CognitiveAgent
from lca.layer3_agent.team_orchestrator import TeamOrchestrator

__all__ = [
    "CognitiveAgent",
    "TeamOrchestrator",
    "TeamProcessStrategyRegistry",
]
```

（相对当前版本：`from lca.layer3_agent.orchestration_registry import (...)` 的导入块去掉 `get_global_orchestration_registry`，`__all__` 去掉对应条目；模块文档字符串不变。）

### 4.4 `lca/layer3_agent/team_orchestrator.py`

```python
"""TeamOrchestrator — team shape, channel, and process strategy."""

from __future__ import annotations

from lca.contracts.enums import DecisionGateName
from lca.contracts.member_status import MemberStatus
from lca.contracts.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols import (
    AgentTransport,
    SharedMemoryStore,
    TeamContext,
    TeamProcessStrategy,
    TeamUnit,
)
from lca.contracts.protocols.capabilities import (
    HasBrainBodyMemory,
    HasChannel,
    HasSharedMemory,
)
from lca.contracts.protocols.cognition import DecisionGate, SupportsDecisionGate
from lca.contracts.registries import Registries
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer3_agent.simple_agent import CognitiveAgent


class TeamOrchestrator(TeamUnit):
    """Resolve process strategy, inject shared memory, bind supervisor setup."""

    def __init__(
        self,
        members: list[CognitiveAgent],
        config: TeamConfig,
        *,
        registries: Registries,
        supervisor: CognitiveAgent | None = None,
        transport: AgentTransport | None = None,
        teammates_text: str = "",
        strategy: TeamProcessStrategy | None = None,
        team_id: str = "",
    ) -> None:
        self.members = members
        self.config = config
        self.supervisor = supervisor
        self.transport = transport
        self.teammates_text = teammates_text
        self.team_id = team_id or f"team-{config.process}"

        if strategy is not None:
            self._strategy = strategy
        else:
            self._strategy = registries.orchestration.resolve(config.process)

        self._shared_store: SharedMemoryStore | None = None
        if config.shared_memory_layers:
            self._shared_store = TeamSharedMemoryStore(config.shared_memory_layers)
            self._inject_shared_memory()

        member_status: MemberStatus | None = None
        if supervisor is not None:
            member_status = self._create_member_status(members, registries)
            policy = self._resolve_decision_gate(config, registries)
            self._bind_supervisor(supervisor, transport, policy)

        self._context = TeamContext(
            members=members,
            config=config,
            supervisor=supervisor,
            transport=transport,
            teammates_text=teammates_text,
            member_status=member_status,
        )

    @staticmethod
    def _create_member_status(
        members: list[CognitiveAgent], registries: Registries
    ) -> MemberStatus:
        required_roles = frozenset(m.role_profile.role for m in members)
        cls = registries.components.require("member_status", "default")
        result = cls(required_roles=required_roles)
        if not isinstance(result, MemberStatus):
            raise TypeError(
                f"member_status factory produced {type(result).__name__}, expected MemberStatus"
            )
        return result

    @staticmethod
    def _resolve_decision_gate(config: TeamConfig, registries: Registries) -> DecisionGate | None:
        policy_name = config.decision_gate if config else DecisionGateName.MUST_CONSULT_ALL
        if policy_name == DecisionGateName.NONE:
            return None
        factory = registries.components.require("decision_gate", policy_name)
        result = factory()
        if not isinstance(result, DecisionGate):
            raise TypeError(
                f"decision_gate factory produced {type(result).__name__}, expected DecisionGate"
            )
        return result

    def _inject_shared_memory(self) -> None:
        if self._shared_store is None:
            return
        for member in self.members:
            if isinstance(member.runtime, HasBrainBodyMemory):
                memory = member.runtime.memory
                if isinstance(memory, HasSharedMemory):
                    memory.bind_shared_memory(self._shared_store)

    @staticmethod
    def _bind_supervisor(
        supervisor: CognitiveAgent,
        transport: AgentTransport | None,
        policy: DecisionGate | None,
    ) -> None:
        """Bind supervisor capabilities at composition time.

        Wires channel and decision gate — the bindings that make an
        agent act as a hierarchical supervisor. Teammates text flows
        through RunContext → AgentState at run time, not here.
        """
        rt = supervisor.runtime
        if not isinstance(rt, HasBrainBodyMemory):
            return
        if transport is not None and isinstance(rt.body, HasChannel):
            rt.body.bind_channel(transport)
        if policy is not None and isinstance(rt, SupportsDecisionGate):
            rt.install_decision_gate(policy)

    async def run(self, objective: str | object) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        return await self._strategy.run(self._context, text)
```

相对当前版本的改动：

1. import 中 `from lca.layer0_infra.component_registry import get_global_registry` 和 `from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry` 两行删除，新增 `from lca.contracts.registries import Registries`。
2. `__init__` 签名新增 `*, registries: Registries`（放在 `*` 之后的第一个参数，因此不占位置参数槽；`supervisor` / `transport` 等原有参数不受影响，只是全部变成显式关键字——这在当前仓库里已经是既成事实：所有真实调用方本来就用关键字传 `supervisor=`）。
3. `self._strategy = get_global_orchestration_registry().resolve(config.process)` 改为 `self._strategy = registries.orchestration.resolve(config.process)`。
4. `_create_member_status(members)` → `_create_member_status(members, registries)`，内部 `get_global_registry().require(...)` 改为 `registries.components.require(...)`。
5. `_resolve_decision_gate(config)` → `_resolve_decision_gate(config, registries)`，同样把 `get_global_registry()` 换成 `registries.components`。
6. 其余方法（`_inject_shared_memory`、`_bind_supervisor`、`run`）逐字不变。

这是本次重构里唯一一处修改了公开构造签名、且没有任何回落路径的地方——故意如此：任何遗漏传参的调用方在导入 / 调用时就会得到 `TypeError: missing required keyword-only argument`，而不是悄悄读到一个内容不确定的全局注册表。

### 4.5 `lca/layer4_app/defaults.py`

```python
"""Built-in default registrations for the LCA framework.

ADR-0024：不再有隐藏的模块级幂等标记。register_defaults() 对调用方传入的
Registries 实例做注册；对同一个 Registries 重复调用是安全的（覆盖写入相同的
工厂，无副作用），生命周期完全交给调用方（通常是 Assembly）决定。

本模块仍然只做发现型注册，不构造可运行对象图（见 assembly.py，ADR-0018）。
"""

from __future__ import annotations

from lca.contracts.enums import DecisionGateName, TeamProcess
from lca.contracts.registries import Registries
from lca.layer0_infra.component_registry import ComponentRegistry, NamedRegistry
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.observability.jsonl_file_observability import JSONLFileObservability
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory
from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer
from lca.layer1_cognitive.event_bus import SimpleEventBus
from lca.layer1_cognitive.member_status import InMemoryMemberStatus
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer3_agent.orchestration_registry import TeamProcessStrategyRegistry
from lca.layer3_agent.orchestration_strategies import (
    ChoreographyStrategy,
    GraphStrategy,
    HierarchicalStrategy,
)


def register_defaults(registries: Registries) -> None:
    """把框架内置的默认实现注册进给定的 *registries*。

    幂等：对同一个 Registries 实例重复调用只是覆盖写入相同的工厂，无害。
    """
    reg = registries.components
    reg.register("observability", "console", ConsoleObservability)
    reg.register("observability", "jsonl_file", JSONLFileObservability)
    reg.register("state_store", "memory", InMemoryStateStore)
    reg.register("memory", "simple", SimpleMemorySystem)
    reg.register("event_bus", "simple", SimpleEventBus)
    reg.register("member_status", "default", InMemoryMemberStatus)

    registries.brain_factories.register("default", SimpleBrainFactory())

    orch = registries.orchestration
    orch.register(TeamProcess.HIERARCHICAL, HierarchicalStrategy)
    orch.register(TeamProcess.SEQUENTIAL, lambda: ChoreographyStrategy("sequential"))
    orch.register(
        TeamProcess.PARALLEL,
        lambda: ChoreographyStrategy("parallel", synthesizer=ConcatSynthesizer()),
    )
    orch.register(TeamProcess.GRAPH, GraphStrategy)
    orch.register(TeamProcess.DEBATE, lambda: ChoreographyStrategy("debate"))
    orch.register(TeamProcess.HANDOFF, lambda: ChoreographyStrategy("handoff"))

    reg.register("decision_gate", DecisionGateName.MUST_CONSULT_ALL, MustConsultAllMembers)


def build_default_registries() -> Registries:
    """构造一份全新的、已注册全部内置默认实现的 Registries。

    这是"给我一份开箱即用的默认组合"的唯一入口 —— Assembly() 在未显式传入
    registries 时用它；测试或需要绕开 Assembly 直接构造 TeamOrchestrator
    的场景也可以直接调用它。
    """
    registries = Registries(
        components=ComponentRegistry(),
        brain_factories=NamedRegistry(),
        orchestration=TeamProcessStrategyRegistry(),
    )
    register_defaults(registries)
    return registries
```

相对当前版本：`register_defaults()` 从无参改为必填 `registries: Registries`，函数体里把 `get_global_registry()` / `get_global_brain_factory_registry()` / `get_global_orchestration_registry()` 三个访问函数的返回值，换成直接使用参数 `registries` 的对应字段；末尾的 `mark_defaults_registered()` 调用删除；`ensure_defaults()` 函数整个删除；新增 `build_default_registries()`。每一条 `register(...)` 调用本身（category、name、目标类）逐字不变。

关于 `tests/test_refactor_guards.py::TestDefaultsNoObjectConstruction.test_defaults_no_object_construction` 这条护栏（用 AST 扫描：对每个函数名不在 `{"register_defaults", "ensure_defaults"}` 集合里的 `FunctionDef`，检查其函数体内的调用是否有名字以 `Transport` 结尾或以 `build_` 开头，若有则判定违规）：`build_default_registries()` 不在豁免集合里，会被扫描，但它函数体内的调用（`Registries(...)`、`ComponentRegistry()`、`NamedRegistry()`、`TeamProcessStrategyRegistry()`、`register_defaults(registries)`）没有一个名字匹配 `*Transport` 或 `build_*` 这两个禁止模式——函数体内调用的是别的函数，不是它自己的函数名——所以这条测试**不需要改代码**就能继续通过。

### 4.6 `lca/layer4_app/assembly.py`

```python
"""Composition root — wires all layers into a working object graph.

Sole module that assembles the full Agent / Team object graphs via the
``Assembly`` class. Entry points: ``Assembly.assemble_agent`` (single agent),
``Assembly.assemble_team`` (team). Lower-level builders:
``build_body_from_shared``, ``build_hooks``.
"""

from __future__ import annotations

from typing import TypeVar

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.budget import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    SUPERVISOR_MIN_MAX_STEPS,
)
from lca.contracts.decision import Observation
from lca.contracts.enums import HookEvent, TeamProcess
from lca.contracts.mechanisms import ComponentRegistryProtocol
from lca.contracts.protocols import (
    AgentTransport,
    Body,
    Brain,
    BrainFactory,
    EventBus,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    TeamProcessStrategy,
    TeamUnit,
    Tool,
    TransportRegistryProtocol,
)
from lca.contracts.registries import Registries
from lca.contracts.role_team import RoleProfile, TeamConfig, ToolPermissionManifest
from lca.layer0_infra.transport.a2a_transport import A2ATransport
from lca.layer0_infra.transport.agent_transport import InternalTransport
from lca.layer0_infra.transport.mcp_transport import MCPTransport
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.fallback_decorated_body import FallbackDecoratedBody
from lca.layer1_cognitive.body.fallback_policy import FallbackActionPolicy
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.brain.reasoner import build_teammates_text
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer2_runtime.default_loop_judge import DefaultStopRule
from lca.layer2_runtime.event_emission import make_event_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.orchestration_registry import OrchestrationFactory
from lca.layer3_agent.simple_agent import CognitiveAgent
from lca.layer4_app.defaults import build_default_registries

T = TypeVar("T")


def _resolve_component(
    reg: ComponentRegistryProtocol,
    category: str,
    value: object,
    expected_type: type[T],
) -> T:
    """Resolve a component from registry or use as-is, with runtime type check."""
    result = reg.require(category, value)() if isinstance(value, str) else value
    if not isinstance(result, expected_type):
        raise TypeError(
            f"{category} expected {expected_type.__name__}, got {type(result).__name__}"
        )
    return result


def build_default_transport_registry() -> TransportRegistry:
    registry = TransportRegistry()
    for t in (InternalTransport(), A2ATransport(), MCPTransport()):
        registry.register(t)
    return registry


async def _call_member_for_channel(member: CognitiveAgent, subtask: str) -> Observation:
    """Invoke a member for InternalTransport."""
    from lca.contracts.delegation_context import get_current_delegator
    from lca.contracts.run_context import RunContext

    from_role = get_current_delegator()
    result = await member.run(subtask, RunContext(from_role=from_role))
    return Observation.from_result(result)


def build_team_transport(
    members: list[CognitiveAgent],
) -> tuple[AgentTransport, str]:
    """Build in-process channel and teammates_text for a team."""
    transport = InternalTransport()
    for member in members:

        async def _handler(subtask: str, _m: CognitiveAgent = member) -> Observation:
            return await _call_member_for_channel(_m, subtask)

        transport.register_agent(member.role_profile.role, _handler)
    return transport, build_teammates_text([m.role_profile for m in members])


def build_body_from_shared(
    tool_registry: SimpleToolRegistry,
    safe_executor: SimpleSafeExecutor,
    transport_registry: TransportRegistryProtocol,
    action_registry: ActionRegistryProtocol,
    *,
    enable_fallback: bool = True,
) -> Body:
    """Build Body from *already-shared* pipeline components.

    The caller must pass the **same** ToolRegistry / SafeExecutor /
    TransportRegistry / ActionRegistry instances that are shared with the
    Brain — never let Body create its own copies.
    """
    simple_body = SimpleBody(
        tool_registry=tool_registry,
        safe_executor=safe_executor,
        transport_registry=transport_registry,
        action_registry=action_registry,
    )
    if enable_fallback:
        return FallbackDecoratedBody(
            inner=simple_body,
            fallback_handler=FallbackActionPolicy(),
            action_registry=action_registry,
        )
    return simple_body


def build_hooks(observability: Observability, event_bus: EventBus) -> SimpleHookRegistry:
    """Build the default HookRegistry with logging + event-emitting hooks."""
    hooks = SimpleHookRegistry(observability)
    event_hook = make_event_emitting_hook(event_bus)
    for event_name in HookEvent:
        hooks.register(event_name, default_logging_hook)
        hooks.register(event_name, event_hook)
    return hooks


def _promote_supervisor(supervisor: CognitiveAgent) -> CognitiveAgent:
    """Apply supervisor budget floors — sole composition decision for team leads."""
    wc = supervisor.max_wall_clock_seconds
    effective_wc = (
        max(wc, DEFAULT_MAX_WALL_CLOCK_SECONDS)
        if wc is not None
        else DEFAULT_MAX_WALL_CLOCK_SECONDS
    )
    return CognitiveAgent(
        supervisor.runtime,
        supervisor.role_profile,
        max_steps=max(supervisor.max_steps, SUPERVISOR_MIN_MAX_STEPS),
        max_wall_clock_seconds=effective_wc,
    )


class Assembly:
    """组合根的显式对象化版本（ADR-0024）。

    持有一份私有的 Registries，不读写任何进程级全局状态。未显式传入
    registries 时，构造一份包含全部内置默认实现的新 Registries
    （见 defaults.build_default_registries）——传入自定义 registries 时，
    按传入的原样使用，不会偷偷叠加内置默认值。
    """

    def __init__(self, registries: Registries | None = None) -> None:
        self._registries = registries if registries is not None else build_default_registries()

    @property
    def registries(self) -> Registries:
        return self._registries

    def register_component(self, category: str, name: str, impl: object) -> None:
        """向本 Assembly 的组件注册表注册自定义实现。

        替代过去"直接改全局 ComponentRegistry"的用法（见 pluggability_demo）。
        """
        self._registries.components.register(category, name, impl)

    def register_brain_factory(self, name: str, factory: BrainFactory) -> None:
        self._registries.brain_factories.register(name, factory)

    def register_orchestration_strategy(
        self, process: TeamProcess, factory: OrchestrationFactory
    ) -> None:
        self._registries.orchestration.register(process, factory)

    def assemble_agent(
        self,
        *,
        role: str,
        goal: str,
        backstory: str,
        tools: list[Tool],
        llm: LLMAdapter,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = DEFAULT_MAX_WALL_CLOCK_SECONDS,
        memory: str | MemorySystem = "simple",
        observability: str | Observability = "console",
        state_store: str | StateStore = "memory",
        brain_strategy: str | Brain = "default",
    ) -> CognitiveAgent:
        """Assemble a complete CognitiveAgent with a single shared pipeline.

        Creates one set of ToolRegistry / SafeExecutor / TransportRegistry /
        ActionRegistry and injects them into both Brain and Body, guaranteeing
        they operate on the same instances. All string-keyed components
        (*memory*, *observability*, *state_store*) are resolved via this
        Assembly's ComponentRegistry.
        """
        reg = self._registries.components

        permission_manifest = ToolPermissionManifest(allowed_tools=[t.name for t in tools])
        role_profile = RoleProfile(
            role=role,
            goal=goal,
            backstory=backstory,
            tool_permission_manifest=permission_manifest,
        )

        # runtime_checkable Protocols support isinstance at runtime; mypy limitation #9208
        obs = _resolve_component(reg, "observability", observability, Observability)  # type: ignore[type-abstract]
        mem = _resolve_component(reg, "memory", memory, MemorySystem)  # type: ignore[type-abstract]
        ss = _resolve_component(reg, "state_store", state_store, StateStore)  # type: ignore[type-abstract]

        tool_registry = SimpleToolRegistry()
        for t in tools:
            tool_registry.register(t)
        safe_executor = SimpleSafeExecutor(permission_manifest, obs)
        transport_registry = build_default_transport_registry()
        action_registry = build_default_action_registry(
            tool_registry, safe_executor, transport_registry
        )

        brain: Brain
        if isinstance(brain_strategy, str):
            strategy_reg = self._registries.brain_factories
            if brain_strategy not in strategy_reg:
                raise ValueError(
                    f"Unknown brain_strategy: {brain_strategy!r}. Available: {strategy_reg.list()}"
                )
            tools_desc = ", ".join(t.name for t in tools) or "(no tools available)"
            factory = strategy_reg.resolve(brain_strategy)
            brain = factory(llm, role_profile, tools_desc, action_registry=action_registry)
        else:
            brain = brain_strategy

        body = build_body_from_shared(
            tool_registry,
            safe_executor,
            transport_registry,
            action_registry,
        )
        event_bus = _resolve_component(reg, "event_bus", "simple", EventBus)  # type: ignore[type-abstract]
        hooks = build_hooks(obs, event_bus)
        runtime = CognitiveRuntime(
            brain,
            body,
            mem,
            hooks,
            ss,
            judge=DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy()),
        )
        return CognitiveAgent(
            runtime,
            role_profile,
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
        )

    def assemble_team(
        self,
        *,
        members: list[CognitiveAgent],
        process: TeamProcess | None = None,
        supervisor: CognitiveAgent | None = None,
        max_rounds: int | None = None,
        shared_memory_layers: list[str] | None = None,
        graph_definition_ref: str | None = None,
        strategy: TeamProcessStrategy | None = None,
    ) -> TeamUnit:
        """Assemble a team object graph from *members* with the given *process*."""
        from lca.layer3_agent.team_orchestrator import TeamOrchestrator

        process_val = process if process is not None else TeamProcess.HIERARCHICAL
        config = TeamConfig(
            process=process_val,
            max_rounds=max_rounds,
            shared_memory_layers=list(shared_memory_layers or []),
            graph_definition_ref=graph_definition_ref,
        )
        base_supervisor = _promote_supervisor(supervisor) if supervisor is not None else None
        transport, teammates_text = build_team_transport(members)

        return TeamOrchestrator(
            members,
            config,
            registries=self._registries,
            supervisor=base_supervisor,
            transport=transport,
            teammates_text=teammates_text,
            strategy=strategy,
        )
```

要点：

- `_resolve_component` 的类型标注从具体类 `ComponentRegistry` 改成 `ComponentRegistryProtocol`——因为调用方 `self._registries.components` 的静态类型现在是这个 Protocol，标注成具体类 mypy 会拒绝。
- `build_default_transport_registry`、`_call_member_for_channel`、`build_team_transport`、`build_body_from_shared`、`build_hooks`、`_promote_supervisor` 六个模块级自由函数逐字不变——`tests/test_refactor_guards.py::TestSupervisorWallClockPropagation` 直接 `from lca.layer4_app.assembly import _promote_supervisor` 调用它，必须保持模块级自由函数不变。
- `assemble_agent` / `assemble_team` 不再需要每次调用都 `ensure_defaults()`：注册这件事在 `Assembly.__init__` 里已经做完一次；`assemble_*` 方法内部不再出现 `ensure_defaults()` / `get_global_registry()` / `get_global_brain_factory_registry()` 三类调用，全部替换为 `self._registries.*`。
- `assemble_team` 里构造 `TeamOrchestrator` 时新增 `registries=self._registries`；同时把原先的位置参数 `base_supervisor` 改成关键字 `supervisor=base_supervisor`——因为 `TeamOrchestrator.__init__` 现在把 `registries` 放在 `*` 之后，`supervisor` 也跟着变成只能关键字传参。这是 `assembly.py` 里唯一因为 `TeamOrchestrator` 签名变化（而不是单纯去全局化）而必须调整的地方。
- `import` 块新增 `ComponentRegistryProtocol`（来自 `mechanisms`）、`BrainFactory`（用于 `register_brain_factory` 的类型标注）、`Registries`、`OrchestrationFactory`（来自 `orchestration_registry`，用于 `register_orchestration_strategy` 的类型标注）、`build_default_registries`；删除 `from lca.layer0_infra.component_registry import ComponentRegistry, get_global_registry`、`from lca.layer2_runtime.strategy_registry import get_global_brain_factory_registry`、`from lca.layer4_app.defaults import ensure_defaults` 三行。

### 4.7 `lca/layer4_app/api.py`

```python
"""Developer-facing API surface.

Import ``Agent`` and ``MultiAgentTeam`` from here (or from the package
root ``lca``). By default they share one lazily-constructed default
``Assembly()``; pass ``assembly=`` to isolate composition state (custom
registered implementations, test isolation).

Example::

    from lca import Agent, MultiAgentTeam
    from lca.contracts.enums import TeamProcess

    researcher = Agent(role="Researcher", goal="Find info", backstory="...",
                       tools=[search_tool], llm=my_llm)
    team = MultiAgentTeam(members=[researcher, writer], process=TeamProcess.SEQUENTIAL)
    result = await team.run("Write a blog post about AI")
"""

from __future__ import annotations

from lca.contracts.budget import DEFAULT_MAX_STEPS, DEFAULT_MAX_WALL_CLOCK_SECONDS
from lca.contracts.enums import TeamProcess
from lca.contracts.protocols import (
    Brain,
    LLMAdapter,
    MemorySystem,
    Observability,
    StateStore,
    TeamProcessStrategy,
    TeamUnit,
    Tool,
)
from lca.contracts.result import Result
from lca.layer4_app.assembly import Assembly

_default_assembly: Assembly | None = None


def _get_default_assembly() -> Assembly:
    global _default_assembly
    if _default_assembly is None:
        _default_assembly = Assembly()
    return _default_assembly


class Agent:
    """A single cognitive agent with role, goal, tools, and an LLM.

    Construct with a role description, a list of tools, and an LLM adapter.
    Call ``await agent.run(task)`` to execute a task through the cognitive
    runtime loop.

    Parameters
    ----------
    role:
        Short role label (e.g. ``"Researcher"``).
    goal:
        What this agent is trying to achieve.
    backstory:
        Narrative context that shapes the agent's behaviour.
    tools:
        Tools available to this agent.
    llm:
        The LLM adapter used for reasoning.
    max_steps:
        Maximum reasoning steps per ``run()`` call.
    max_wall_clock_seconds:
        Hard wall-clock timeout; ``None`` for no limit.
    memory:
        ``"simple"`` (default) or a ``MemorySystem`` instance.
    observability:
        ``"console"`` (default), ``"jsonl_file"``, or an ``Observability`` instance.
    state_store:
        ``"memory"`` (default) or a ``StateStore`` instance.
    brain_strategy:
        ``"default"`` or a registered strategy name / ``Brain`` instance.
    assembly:
        Optional. Pass your own ``Assembly`` to isolate composition state
        (e.g. custom registered implementations, or test isolation); when
        omitted, the process-default lazily-constructed Assembly is used.
    """

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        tools: list[Tool],
        llm: LLMAdapter,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = DEFAULT_MAX_WALL_CLOCK_SECONDS,
        memory: str | MemorySystem = "simple",
        observability: str | Observability = "console",
        state_store: str | StateStore = "memory",
        brain_strategy: str | Brain = "default",
        assembly: Assembly | None = None,
    ) -> None:
        target = assembly or _get_default_assembly()
        self._agent = target.assemble_agent(
            role=role,
            goal=goal,
            backstory=backstory,
            tools=tools,
            llm=llm,
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
            memory=memory,
            observability=observability,
            state_store=state_store,
            brain_strategy=brain_strategy,
        )

    async def run(self, task: str) -> Result:
        """Execute *task* and return the result."""
        return await self._agent.run(task)


class MultiAgentTeam:
    """A team of agents coordinated by a shared orchestration process.

    Parameters
    ----------
    members:
        The agents participating in this team.
    process:
        Orchestration pattern (hierarchical, sequential, parallel, etc.).
    supervisor:
        Optional supervisor agent (required for ``HIERARCHICAL`` process).
    max_rounds:
        Maximum coordination rounds; ``None`` for unlimited.
    shared_memory_layers:
        Memory layers shared across team members.
    graph_definition_ref:
        Reference to a graph definition (for ``GRAPH`` process).
    strategy:
        Optional custom ``TeamProcessStrategy`` override.
    assembly:
        Optional. Pass your own ``Assembly`` to isolate composition state;
        when omitted, the process-default lazily-constructed Assembly is used.
    """

    def __init__(
        self,
        members: list[Agent],
        process: TeamProcess = TeamProcess.HIERARCHICAL,
        supervisor: Agent | None = None,
        max_rounds: int | None = None,
        shared_memory_layers: list[str] | None = None,
        graph_definition_ref: str | None = None,
        strategy: TeamProcessStrategy | None = None,
        assembly: Assembly | None = None,
    ) -> None:
        target = assembly or _get_default_assembly()
        base_members = [m._agent for m in members]
        base_supervisor = supervisor._agent if supervisor else None
        self._orchestrator: TeamUnit = target.assemble_team(
            members=base_members,
            process=process,
            supervisor=base_supervisor,
            max_rounds=max_rounds,
            shared_memory_layers=shared_memory_layers,
            graph_definition_ref=graph_definition_ref,
            strategy=strategy,
        )

    async def run(self, objective: str) -> Result:
        """Run the team on *objective* and return the aggregated result."""
        return await self._orchestrator.run(objective)
```

相对当前版本：模块文档字符串把"thin wrappers around the composition root (assembly) that handle default registration"改为"share one lazily-constructed default Assembly()"；import 里 `from lca.layer4_app.assembly import assemble_agent, assemble_team` 和 `from lca.layer4_app.defaults import ensure_defaults` 两行删除，改为 `from lca.layer4_app.assembly import Assembly`；新增模块级 `_default_assembly` 单例和 `_get_default_assembly()` 辅助函数；`Agent.__init__` / `MultiAgentTeam.__init__` 都新增可选 `assembly: Assembly | None = None` 参数，函数体开头从 `ensure_defaults()` 改为 `target = assembly or _get_default_assembly()`，随后把 `assemble_agent(...)` / `assemble_team(...)` 的模块级函数调用改成 `target.assemble_agent(...)` / `target.assemble_team(...)` 的方法调用；两个类文档字符串的 Parameters 部分各新增一条 `assembly:` 说明；`run()` 方法逐字不变。

`from lca import Agent; Agent(role=..., ...)` 三行体验一个字符不变；想要隔离状态的用户多写两行：

```python
from lca.layer4_app.assembly import Assembly

my_assembly = Assembly()
agent = Agent(role=..., ..., assembly=my_assembly)
```

---

## 5. `examples/pluggability_demo/pluggability_demo.py`：可插拔场景改法

这是全仓库里唯一一处"运行前注册自定义实现"的真实（非测试）用例。`main()` 函数顶部和底部各有对 `get_global_registry()` 返回值 `reg` 的引用：

```python
# 旧
from lca.layer0_infra.component_registry import get_global_registry

...


async def main() -> None:
    llm = MockLLMAdapter()
    calculator = CalculatorTool()

    # --- 方式 1: 通过注册表名字注入自定义 MemorySystem ---
    reg = get_global_registry()
    reg.register("memory", "logging", LoggingMemorySystem)
    ...
    agent_with_logging_memory = Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算。",
        tools=[calculator],
        llm=llm,
        memory="logging",
    )
    ...
    agent_with_custom_obs = Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算。",
        tools=[calculator],
        llm=llm,
        observability=my_obs,
    )
    ...
    # --- 验证注册表列表 ---
    print()
    print("已注册的 memory 实现:", reg.list("memory"))
    print("已注册的 observability 实现:", reg.list("observability"))
```

```python
# 新
from lca.layer4_app.assembly import Assembly

...


async def main() -> None:
    llm = MockLLMAdapter()
    calculator = CalculatorTool()

    # --- 方式 1: 通过注册表名字注入自定义 MemorySystem ---
    assembly = Assembly()
    assembly.register_component("memory", "logging", LoggingMemorySystem)
    ...
    agent_with_logging_memory = Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算。",
        tools=[calculator],
        llm=llm,
        memory="logging",
        assembly=assembly,
    )
    ...
    agent_with_custom_obs = Agent(
        role="通用问答助手",
        goal="准确、简洁地回答用户提出的问题",
        backstory="擅长借助工具进行精确计算。",
        tools=[calculator],
        llm=llm,
        observability=my_obs,
        assembly=assembly,
    )
    ...
    # --- 验证注册表列表 ---
    print()
    print("已注册的 memory 实现:", assembly.registries.components.list("memory"))
    print("已注册的 observability 实现:", assembly.registries.components.list("observability"))
```

三处调用点都要改到位：`get_global_registry()` → `Assembly()`；两个 `Agent(...)` 构造调用都新增 `assembly=assembly`（否则第二个 `Agent` 会用默认的懒加载 `Assembly`，看不到第一个 `Agent` 注册的 `"logging"` memory 实现，虽然本例不影响，但保持同一个 `assembly` 是正确的可插拔性演示）；末尾两行 `reg.list(...)` 都要改成 `assembly.registries.components.list(...)`（原代码这里是两行，都引用了 `reg`，不是只有 `memory` 那一行）。第二段"直接传实例"的 `MinimalObservability` 用法本来就不经过注册表，不受影响。

---

## 6. 全仓库改动清单

| 文件 | 改动类型 |
|---|---|
| `lca/contracts/mechanisms.py` | 新增 `ComponentRegistryProtocol`；模块文档字符串一处措辞更新 |
| `lca/contracts/registries.py` | **新增文件**：`Registries` |
| `lca/contracts/protocols/__init__.py` | re-export `ComponentRegistryProtocol`，`__all__` 追加 |
| `lca/contracts/__init__.py` | 顶层 re-export `Registries`、`ComponentRegistryProtocol`，`__all__` 追加 |
| `lca/layer0_infra/component_registry.py` | 删 `_global_registry` / `get_global_registry` / `_defaults_registered` / `defaults_registered` / `mark_defaults_registered`，只留三个类；`ComponentRegistry` 文档字符串一处措辞更新 |
| `lca/layer2_runtime/strategy_registry.py` | **整个文件删除** |
| `lca/layer2_runtime/__init__.py` | 删 `get_global_brain_factory_registry` 的 import / `__all__` |
| `lca/layer3_agent/orchestration_registry.py` | 删 `_global_orchestration_registry` / `get_global_orchestration_registry`，留 `TeamProcessStrategyRegistry`；模块文档字符串追加 ADR-0024 说明 |
| `lca/layer3_agent/__init__.py` | 删 `get_global_orchestration_registry` 的 import / `__all__` |
| `lca/layer3_agent/team_orchestrator.py` | `__init__` 新增必填 `registries: Registries`（keyword-only）；`_create_member_status` / `_resolve_decision_gate` 签名加 `registries` 参数 |
| `lca/layer4_app/defaults.py` | `register_defaults` 参数改必填；删 `ensure_defaults` 等三个函数；新增 `build_default_registries()` |
| `lca/layer4_app/assembly.py` | 新增 `Assembly` 类（含 `register_component` 等三个方法）；`assemble_agent` / `assemble_team` 从模块函数变方法；六个 helper 自由函数逐字不变 |
| `lca/layer4_app/api.py` | `Agent` / `MultiAgentTeam` 新增可选 `assembly` 参数；新增唯一的 `_default_assembly` 懒加载单例 |
| `examples/pluggability_demo/pluggability_demo.py` | 改用 `Assembly().register_component(...)`，两处 `Agent(...)` 加 `assembly=`，两行 `reg.list(...)` 改为 `assembly.registries.components.list(...)` |
| `docs/registry-catalog.md` | 更新"生命周期"/"注册点"两列 + 硬不变量 #3 措辞 + "入口"一节 |
| `docs/glossary.md` | 新增 `Registries`、`Assembly` 两条词条 |
| `docs/adr/README.md` | 新增 `[0024]` 一行（`tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 要求文件名前缀与索引一一对应） |
| `docs/adr/0024-registries-value-object.md` | **新增**（本文档） |
| `tests/test_debate_strategy.py` | 见 §7.2 |
| `tests/test_debate_strategy_conflict_gap.py` | 见 §7.4 |
| `tests/test_graph_strategy.py` | 见 §7.3 |
| `tests/test_handoff_strategy.py` | 见 §7.2 |
| `tests/test_orchestration_coverage.py` | 见 §7.2 |
| `tests/test_parallel_strategy.py` | 见 §7.3 |
| `tests/test_protocol_compliance.py` | 见 §7.1 |
| `tests/test_shared_memory_isolation.py` | 见 §7.1 |
| `tests/test_step4_supervisor_bind_team.py` | 见 §7.1 |

`lca/layer0_infra/component_registry.py`、`lca/layer2_runtime/strategy_registry.py`（除删除本身外）、`lca/layer3_agent/orchestration_registry.py` 之外的其余 L0-L3 文件——零改动。

---

## 7. 测试改造范式

9 个测试文件按它们对全局单例的真实依赖方式，分成三类改法。

### 7.1 直接构造 `TeamOrchestrator(...)` 或直接查 brain_factories 注册表——需要 `registries=`

**`tests/test_step4_supervisor_bind_team.py`**：模块顶部有 `ensure_defaults()` 副作用调用，文件内共有 4 处 `TeamOrchestrator(...)` 构造：

```python
# 旧（模块顶部）
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()
```

```python
# 新（模块顶部）
from lca.layer4_app.defaults import build_default_registries

_REGISTRIES = build_default_registries()
```

4 处调用点分别加 `registries=_REGISTRIES`：

```python
# 旧
orchestrator = TeamOrchestrator(
    members,
    config,
    supervisor=sup,
    transport=transport,
    teammates_text=teammates_text,
)
# 新
orchestrator = TeamOrchestrator(
    members,
    config,
    registries=_REGISTRIES,
    supervisor=sup,
    transport=transport,
    teammates_text=teammates_text,
)
```

（同样的模式出现两次，分别在 `test_orchestrator_binds_transport_to_body` 和 `test_orchestrator_carries_roster_in_context` 里）

```python
# 旧
orchestrator = TeamOrchestrator(members, config, supervisor=sup)
# 新
orchestrator = TeamOrchestrator(members, config, registries=_REGISTRIES, supervisor=sup)
```

（`test_orchestrator_without_transport_skips_bind` 里）

```python
# 旧
orchestrator = TeamOrchestrator([], config, supervisor=None)
# 新
orchestrator = TeamOrchestrator([], config, registries=_REGISTRIES, supervisor=None)
```

（`test_hierarchical_requires_supervisor` 里）

**`tests/test_protocol_compliance.py`**：不在模块顶部调用 `ensure_defaults()`，两处需要局部改动。

```python
# 旧（TestL3ProtocolCompliance.test_team_orchestrator_is_team_runtime）
def test_team_orchestrator_is_team_runtime(self):
    from lca.contracts.role_team import TeamConfig
    from lca.layer3_agent.team_orchestrator import TeamOrchestrator

    agent, _rp, _runtime = self._build_agent()
    config = TeamConfig(process="sequential")
    orchestrator = TeamOrchestrator([agent], config)
    self.assertIsInstance(orchestrator, TeamUnit)
```

```python
# 新
def test_team_orchestrator_is_team_runtime(self):
    from lca.contracts.role_team import TeamConfig
    from lca.layer3_agent.team_orchestrator import TeamOrchestrator
    from lca.layer4_app.defaults import build_default_registries

    agent, _rp, _runtime = self._build_agent()
    config = TeamConfig(process="sequential")
    orchestrator = TeamOrchestrator([agent], config, registries=build_default_registries())
    self.assertIsInstance(orchestrator, TeamUnit)
```

```python
# 旧（TestBrainFactoryRegistryIntegration.test_default_strategy_registered）
def test_default_strategy_registered(self):
    from lca.layer2_runtime.strategy_registry import get_global_brain_factory_registry

    reg = get_global_brain_factory_registry()
    self.assertIn("default", reg)
```

```python
# 新
def test_default_strategy_registered(self):
    from lca.layer4_app.defaults import build_default_registries

    registries = build_default_registries()
    self.assertIn("default", registries.brain_factories)
```

`test_agent_with_string_strategy`、`test_agent_with_custom_strategy`、`test_agent_with_unknown_strategy_raises` 三个用例都走 `Agent(...)`（L4 门面），完全不用改——它们通过默认 `Assembly` 间接拿到默认注册表。

**`tests/test_shared_memory_isolation.py`**：该文件本来没有任何 `ensure_defaults()` 或 `get_global_*` 引用——它此前能跑通，靠的是别的测试模块导入时的副作用把全局注册表填好了（pytest 收集顺序耦合，属于当前设计的隐藏脆弱性，见 §11）。文件内两处 `TeamOrchestrator(members=[agent_a, agent_b], config=config)` 都是局部 import：

```python
# 旧（test_orchestrator_injects_shared_memory 内）
from lca.layer3_agent.team_orchestrator import TeamOrchestrator

orchestrator = TeamOrchestrator(members=[agent_a, agent_b], config=config)
```

```python
# 新
from lca.layer3_agent.team_orchestrator import TeamOrchestrator
from lca.layer4_app.defaults import build_default_registries

orchestrator = TeamOrchestrator(
    members=[agent_a, agent_b], config=config, registries=build_default_registries()
)
```

（`test_orchestrator_no_shared_memory_when_config_empty` 里的第二处调用做同样的修改。）两处调用都没有传 `supervisor`，因此 `_create_member_status` / `_resolve_decision_gate` 不会被触发；`registries` 唯一被用到的地方是 `registries.orchestration.resolve(config.process)`（`config.process="sequential"`），所以只要 `Registries.orchestration` 里注册了 `"sequential"` 就够——`build_default_registries()` 满足这个条件。

### 7.2 直接查 `orchestration` 注册表，但不改测试方法名

**`tests/test_debate_strategy.py`**、**`tests/test_handoff_strategy.py`**、**`tests/test_orchestration_coverage.py`**：三个文件的模式相同——模块顶部导入 `get_global_orchestration_registry` 和 `ensure_defaults`，调用 `ensure_defaults()`，随后在类方法体内直接调用 `get_global_orchestration_registry()`。

```python
# 旧（三个文件模块顶部模式相同，以 test_debate_strategy.py 为例）
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.orchestration_strategies import ChoreographyStrategy
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()
```

```python
# 新
from lca.layer3_agent.orchestration_strategies import ChoreographyStrategy
from lca.layer4_app.defaults import build_default_registries

_REGISTRIES = build_default_registries()
```

`test_debate_strategy.py` 的 `TestDebateStrategyRegistration`：

```python
# 旧
def test_debate_registered_in_global_registry(self) -> None:
    registry = get_global_orchestration_registry()
    self.assertTrue(registry.has("debate"))


def test_debate_resolves_to_debate_strategy(self) -> None:
    registry = get_global_orchestration_registry()
    strategy = registry.resolve("debate")
    self.assertIsInstance(strategy, ChoreographyStrategy)
```

```python
# 新（第一个方法改名，"global registry" 措辞不再准确）
def test_debate_registered_by_default(self) -> None:
    registry = _REGISTRIES.orchestration
    self.assertTrue(registry.has("debate"))


def test_debate_resolves_to_debate_strategy(self) -> None:
    registry = _REGISTRIES.orchestration
    strategy = registry.resolve("debate")
    self.assertIsInstance(strategy, ChoreographyStrategy)
```

`test_handoff_strategy.py` 的 `TestHandoffRegistration`（方法名本来就不含"global_registry"字样，不用改名）：

```python
# 旧
def test_handoff_registered(self) -> None:
    registry = get_global_orchestration_registry()
    self.assertTrue(registry.has("handoff"))


def test_handoff_resolves(self) -> None:
    registry = get_global_orchestration_registry()
    strategy = registry.resolve("handoff")
    self.assertIsInstance(strategy, ChoreographyStrategy)
```

```python
# 新
def test_handoff_registered(self) -> None:
    registry = _REGISTRIES.orchestration
    self.assertTrue(registry.has("handoff"))


def test_handoff_resolves(self) -> None:
    registry = _REGISTRIES.orchestration
    strategy = registry.resolve("handoff")
    self.assertIsInstance(strategy, ChoreographyStrategy)
```

`test_orchestration_coverage.py` 的 `TestOrchestrationCoverage`（两处调用，方法名不含"global_registry"字样）：

```python
# 旧
def test_literal_values_match_registered_strategies(self) -> None:
    literal_values = _get_process_enum_values()
    registered = set(get_global_orchestration_registry().list_strategies())
    ...


def test_resolve_unknown_strategy_raises_value_error(self) -> None:
    registry = get_global_orchestration_registry()
    with self.assertRaises(ValueError) as ctx:
        registry.resolve("nonexistent_strategy")
    ...
```

```python
# 新
def test_literal_values_match_registered_strategies(self) -> None:
    literal_values = _get_process_enum_values()
    registered = set(_REGISTRIES.orchestration.list_strategies())
    ...


def test_resolve_unknown_strategy_raises_value_error(self) -> None:
    registry = _REGISTRIES.orchestration
    with self.assertRaises(ValueError) as ctx:
        registry.resolve("nonexistent_strategy")
    ...
```

（该文件另外两个用例 `test_graph_strategy_requires_execution_graph`、`test_debate_strategy_is_functional` 直接构造 `GraphStrategy()` / `ChoreographyStrategy("debate")`，不经过注册表，不用改。）

### 7.3 直接查 `orchestration` 注册表，且需要改测试方法名

**`tests/test_graph_strategy.py`**：`get_global_orchestration_registry` 不是模块顶部导入，而是在 `TestGraphStrategyRegistration` 的两个方法体内各自局部 import 一次；模块顶部只有 `ensure_defaults()`，且全文件唯一用到它的地方就是这两个方法。

```python
# 旧（模块顶部）
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()
```

```python
# 新（模块顶部）——不再需要，整段删除，不用替换成 _REGISTRIES
```

```python
# 旧
class TestGraphStrategyRegistration(unittest.TestCase):
    """GraphStrategy 注册与解析。"""

    def test_graph_registered_in_global_registry(self) -> None:
        from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry

        registry = get_global_orchestration_registry()
        self.assertTrue(registry.has("graph"))

    def test_graph_resolves_correctly(self) -> None:
        from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry

        registry = get_global_orchestration_registry()
        strategy = registry.resolve("graph")
        self.assertIsInstance(strategy, GraphStrategy)
```

```python
# 新
class TestGraphStrategyRegistration(unittest.TestCase):
    """GraphStrategy 注册与解析。"""

    def test_graph_registered_by_default(self) -> None:
        from lca.layer4_app.defaults import build_default_registries

        registry = build_default_registries().orchestration
        self.assertTrue(registry.has("graph"))

    def test_graph_resolves_correctly(self) -> None:
        from lca.layer4_app.defaults import build_default_registries

        registry = build_default_registries().orchestration
        strategy = registry.resolve("graph")
        self.assertIsInstance(strategy, GraphStrategy)
```

**`tests/test_parallel_strategy.py`**：`get_global_orchestration_registry` 是模块顶部导入，和 `ensure_defaults()` 一起。

```python
# 旧（模块顶部）
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.layer3_agent.orchestration_strategies import ChoreographyStrategy
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()
```

```python
# 新
from lca.layer3_agent.orchestration_strategies import ChoreographyStrategy
from lca.layer4_app.defaults import build_default_registries

_REGISTRIES = build_default_registries()
```

```python
# 旧
class TestParallelStrategyRegistration(unittest.TestCase):
    """ParallelStrategy 已注册到全局 registry，且与 TeamConfig.process Literal 对齐。"""

    def test_parallel_registered_in_global_registry(self) -> None:
        registry = get_global_orchestration_registry()
        self.assertTrue(registry.has("parallel"))

    def test_parallel_resolves_correctly(self) -> None:
        registry = get_global_orchestration_registry()
        strategy = registry.resolve("parallel")
        self.assertIsInstance(strategy, ChoreographyStrategy)
```

```python
# 新
class TestParallelStrategyRegistration(unittest.TestCase):
    """ParallelStrategy 默认已注册，且与 TeamConfig.process Literal 对齐。"""

    def test_parallel_registered_by_default(self) -> None:
        registry = _REGISTRIES.orchestration
        self.assertTrue(registry.has("parallel"))

    def test_parallel_resolves_correctly(self) -> None:
        registry = _REGISTRIES.orchestration
        strategy = registry.resolve("parallel")
        self.assertIsInstance(strategy, ChoreographyStrategy)
```

### 7.4 只调用了 `ensure_defaults()` 作为安全网，从未直接碰注册表

**`tests/test_debate_strategy_conflict_gap.py`**：全文件只用 `Agent` / `MultiAgentTeam`（L4 门面），`ensure_defaults()` 只是构造它们之前的安全网，不需要任何 `Registries` 替代——直接删除即可。

```python
# 旧（模块顶部）
from lca.contracts.protocols import LLMAdapter
from lca.layer4_app.api import Agent, MultiAgentTeam
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()
```

```python
# 新（模块顶部）
from lca.contracts.protocols import LLMAdapter
from lca.layer4_app.api import Agent, MultiAgentTeam
```

文件其余部分（`DebatePricingLLM`、`TestDebateStrategyCapability`）逐字不变——`Agent(...)` / `MultiAgentTeam(...)` 内部通过默认 `Assembly` 自动完成注册。

### 7.5 隐藏耦合说明

这次改造顺带修掉一个现存的隐藏脆弱性：目前 `test_shared_memory_isolation.py`（§7.1）能通过，靠的不是自己调用 `ensure_defaults()`，而是 pytest 收集运行时别的测试模块导入时已经把全局注册表填好了——测试之间通过一份进程级可变状态耦合，理论上受 pytest 收集顺序影响。改完之后每个测试自己构造 `Registries`（模块级一次或每个测试方法各一次），互相之间不再共享任何可变状态，隔离性比现在更好，不是纯粹的等价替换。

---

## 8. 文档同步

### 8.1 `docs/registry-catalog.md`

完整替换为：

```markdown
# 注册表地图（发现型 vs 运行时绑定型）

| 种类 | 注册表 | 键 | 找不到时 | 生命周期 | 注册点 |
|------|--------|----|----------|----------|--------|
| **发现型** | `ComponentRegistry` | `(category, name)` | `get`→None / `require`→raise | 每个 `Assembly` 实例持有一份（`Registries.components`） | `Assembly.__init__` → `defaults.register_defaults` |
| **发现型** | `NamedRegistry[BrainFactory]` | brain 策略名 | `resolve`→raise | 同上（`Registries.brain_factories`） | 同上 |
| **发现型** | `TeamProcessStrategyRegistry` | process 名 | `resolve`→raise | 同上（`Registries.orchestration`） | 同上 |
| **运行时** | `ActionRegistry` | action_type | `resolve`→None | 每 Agent 一份，assembly 注入 | `action_catalog.build_default_action_registry` |
| **运行时** | `ToolRegistry` | tool name | `get`→None | 与 Action 共享同一实例 | `assemble_agent` |
| **运行时** | `TransportRegistry` | protocol_name | `resolve`→raise | 每 Agent / 团队 | `build_default_transport_registry` |
| **横切** | `HookRegistry` | event_name→多 hook | n/a | 每 Runtime | `assembly.build_hooks` |

## 硬不变量

1. **Body 与 DecisionParser 必须共享同一 `ActionRegistry` 实例。**
2. **`UseToolOperation` 闭包内的 `ToolRegistry` 必须与 `SimpleBody.tool_registry` 为同一对象**（否则 `SharedMemoryTool` 注入失效）。
3. 业务层（L0–L3）不得读写进程级全局可变状态；所需的 `Registries` 必须由调用方显式传入（最终来自某个 `Assembly` 实例）。

## 入口

- 完整对象图：`lca.layer4_app.assembly.Assembly.assemble_agent`
- 默认发现注册：`lca.layer4_app.defaults.build_default_registries`
```

### 8.2 `docs/glossary.md`

在"L-Plugin / L0"表格的 `**ComponentRegistry** / **NamedRegistry**` 一行之后新增两行：

```markdown
| **Registries** | 三个发现型注册表的值对象包（components / brain_factories / orchestration），Assembly 私有持有，替代进程级全局单例（ADR-0024） |
| **Assembly** | 组合根的显式对象化版本，持有一份 Registries；`assemble_agent` / `assemble_team` 是其方法（原模块级自由函数） |
```

### 8.3 `docs/adr/README.md`

在 `[0023]` 一行之后追加：

```markdown
| [0024](0024-registries-value-object.md) | Registries 值对象取代全局单例 | 三个 get_global_* 删除；TeamOrchestrator/Assembly 显式传递 Registries |
```

---

## 9. 验收标准

严格按 `AGENTS.md` 规定的顺序跑完，一步都不能跳：

```bash
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports        # 重点验证：contracts/registries.py 不触发契约 3
uv run mypy lca            # 重点验证：ComponentRegistryProtocol 结构类型对得上
uv run pytest              # 重点验证：本文档列出的 9 个测试文件全部更新到位
uv run vulture lca --min-confidence 80  # 重点验证：三个被删除的 get_global_* 没有残留死引用
```

额外针对本次改动的检查点：

- `tests/test_refactor_guards.py` 全部断言不需要改代码就应该继续通过：
  - `TestDefaultsNoObjectConstruction.test_defaults_no_object_construction`：`build_default_registries()` 函数体内的调用（`Registries`、`ComponentRegistry`、`NamedRegistry`、`TeamProcessStrategyRegistry`、`register_defaults`）都不匹配 `*Transport` / `build_*` 两个禁止模式（见 §4.5 末尾说明）。
  - `TestSupervisorWallClockPropagation.test_supervisor_wall_clock_preserved`：`_promote_supervisor` 保持模块级自由函数，签名不变（见 §4.6）。
  - `TestAdrIndexMatchesFilesystem.test_adr_index_matches_filesystem`：新增的 `docs/adr/0024-registries-value-object.md` 文件名前缀 `0024-` 与 `docs/adr/README.md` 里新增的 `[0024]` 索引一一对应（见 §8.3）。
  - `TestProgressiveDisclosureVocabulary.test_public_api_uses_run_and_assemble_agent`：新 `api.py` 内含子串 `"assemble_agent"`、`"async def run"`、`"await self._agent.run"`；新 `assembly.py` 内含子串 `"def assemble_agent"`（作为 `Assembly` 的方法定义行，子串匹配不受缩进影响）——§4.6/§4.7 的最终版本都满足。
- `tests/test_contracts_purity.py`：`Registries` 是零方法 `@dataclass(frozen=True)`，且非 Protocol/非异常/非枚举——不需要加进 `_GRANDFATHERED_METHODS` 例外表就能通过（见 §3.2）。
- `tests/test_layer_boundary.py`：只扫描 `lca/layer3_agent/` 下对 `getattr(x.runtime, "body"/"brain"/"memory"/"hooks")` 的裸穿透模式；本次改动没有在 `team_orchestrator.py` 引入这类调用，不受影响。
- 全局搜索确认无残留：`grep -rn "get_global_registry\|get_global_brain_factory_registry\|get_global_orchestration_registry\|ensure_defaults\b" lca/ tests/ examples/` 应该零命中（除本 ADR 文档和历史 ADR（ADR-0018、ADR-0021、ADR-0023）里作为"过去的设计"提及之外）。

---

## 10. 考虑过的替代方案

### 10.1 渐进式双轨过渡（保留全局单例作为逃生舱）

保留三个 `get_global_*()` 函数作为向后兼容的逃生舱，`TeamOrchestrator.registries` 参数设为可选，缺省时回落到全局单例；新代码可以选择传 `registries=`，旧代码不用动。

放弃理由：两条路径长期并存会使"消灭全局可变状态"这一目标落空——旧调用方可以永远不迁移，新旧行为在同一进程里同时存在，且类型系统无法强制新代码走新路径。`docs/registry-catalog.md` 和 `AGENTS.md` 已经明文写下的规则（业务层不摸全局、协作方通过构造函数注入）值得被一次性认真执行，而不是留一个"新代码走新路径、旧代码继续摸全局"的过渡期。项目在 ADR-0019（删除 `GroupChat` 模块、删除 `Supervisor` 空壳子类）和 ADR-0023 §5（溶解 `BrainFactoryRegistry` 包装类）中已有先例，均属于"一次做完、明确列出破坏性变更"的清理方式，本次决定与既有做法保持一致。

### 10.2 让 `Registries` 字段带具体类型默认值

即给 `Registries` 的字段加 `default_factory`，例如 `components: ComponentRegistryProtocol = field(default_factory=lambda: ComponentRegistry())`，让 `Registries()` 不带参数也能直接可用，省去 `build_default_registries()` 这一层。

放弃理由：`default_factory` 要构造出真正能用的 `ComponentRegistry()` 实例，就必须在 `lca.contracts` 内部 `import lca.layer0_infra.component_registry`——而 `pyproject.toml` 中的 import-linter 契约 3（"contracts 纯净性：不得依赖任何具体实现"，`source_modules = ["lca.contracts"]`，`forbidden_modules` 包含 `"lca.layer0_infra"`）明确禁止这条依赖方向。这条路径一旦写出来，`uv run lint-imports` 会直接报错。因此默认实例的构造必须下沉到组合根 `layer4_app`（见 §4.5 `build_default_registries()`），`Registries` 本身保持"零依赖、纯 Protocol 形状声明"。

### 10.3 彻底删除 `api.py` 里的 `_default_assembly`，让 `Agent(...)` 也必须显式传 `assembly=`

即不保留任何进程级懒加载单例，任何构造 `Agent` / `MultiAgentTeam` 的地方都必须先手动 `Assembly()` 再传入。

放弃理由：会破坏 `from lca import Agent; Agent(role=..., ...)` 三行体验——这是 ADR-0005 定下的、目前唯一一处刻意保留的框架级人体工程学优惠（该 ADR 明确把"`layer4_app/api.py` 是开发者唯一接触的入口——三行创建 Agent"列为决定的一部分）。保留一个单一、封装良好、可被显式绕开的懒加载单例，是"完全消灭全局状态"和"保留三行上手体验"之间唯一自洽的折中；且它和被删除的三个单例有本质区别——它不是"到处都能摸到的裸字典"，而是被 `Assembly` 封装、可以被任何调用方一行代码整体替换掉的对象。

---

## 11. 已知限制与后续

- `api.py` 里的 `_default_assembly` 是全仓库唯一残留的进程级可变状态。它没有加锁——对这个框架当前"单进程内构造几个 Agent/Team"的典型用法足够；如果未来要支持多线程并发首次构造，需要补一个双检锁或改成模块导入时立即构造（牺牲"零副作用 import"换线程安全），这个取舍本 ADR 不预先决定。
- `TeamOrchestrator.__init__` 的 `registries` 参数没有类型层面强制"这份 `Registries` 必须包含 `member_status` / `decision_gate` 等特定 category"——如果调用方传入一份没注册这些的 `Registries`，失败发生在 `require()` 抛 `RegistryKeyError` 的那一刻，而不是构造 `TeamOrchestrator` 的那一刻。这是现状的延续（原来全局注册表同样可能缺注册），本次改动没有让这一点变得更差，也没有让它变得更好。
- 这份方案要求同一个 PR 里改完 §6 清单中列出的全部文件——14 个源码文件（含 1 个整体删除的文件）、3 篇既有文档、新增的本 ADR 文档，以及 9 个测试文件。落地前建议用 `git log --since="2 weeks ago" -- tests/test_debate_strategy.py tests/test_graph_strategy.py ...`（对 §6 列出的 9 个测试文件逐一执行）确认这些文件近期没有未合并的并行改动，降低合并冲突风险。
