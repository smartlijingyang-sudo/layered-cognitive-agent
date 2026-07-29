# 彻底重构方案

> 原则：**修根因，不搬文件。** 每一条改动都必须回答"它解决了什么架构病根"。

---

## 病根总览

| # | 根因 | 症状 | 影响范围 |
|---|------|------|---------|
| R1 | 组合根 = Service Locator + 注册/装配/兼容三合一 | `assembly.py` ↔ `defaults.py` 循环懒加载 | 架构根基 |
| R2 | 可观测性关注点侵入认知层 | `hook_registry.py`（L1）包含密钥脱敏 + span 属性提取 | 层级纪律 |
| R3 | MAP 模块与 Pipeline 双轨并存 | `map_modules/` 有 Protocol 实现，Pipeline 内联了简化版 | 漂移风险 |
| R4 | 死代码未清理 | `guarded_coordinator.py`、`SkillRecord`、`KGTriple` | 认知负担 |
| R5 | Protocol 演进无治理 | `perceive`/`perceive_and_retrieve` 别名共存 | API 清晰度 |
| R6 | 文件归属随意 | `prompt_manager.py` 在 L1 顶层、`SharedMemoryTool` 在 L3 | 导航成本 |

---

## Phase 1：组合根去 Service Locator（根因 R1）

### 当前病根

`defaults.py` 同时承担三个职责：
1. **类注册**：`register_defaults()` 把实现类注册到全局 `ComponentRegistry`
2. **工厂注册**：`_default_brain_factory` 反向 import `assembly.build_default_brain`
3. **兼容适配**：`_DEPRECATED_BUILDERS` + `__getattr__` 做废弃符号转发

职责 2 造成了 `defaults.py → assembly.py` 的反向依赖，职责 3 又叠加了兼容包袱。

### 根治方案：类注册表 + 装配时构造

**核心思想**：`defaults.py` 只注册**类/工厂**，不注册**需要 assembly 才能构造的复合对象**。
Assembly 负责所有"需要知道其他组件才能构造"的逻辑。

```
之前：defaults.py 注册 lambda: DebateStrategy(conflict_monitor=..., ...)  ← 需要 import 具体类
之后：defaults.py 注册 {"conflict_monitor": "map", "task_coordinator": "map", ...}  ← 只注册类
      assembly.py 读取映射，构造实例
```

#### 1a. `defaults.py` 瘦身 —— 只保留类映射

```python
# defaults.py —— 重构后

from lca.layer0_infra.component_registry import (
    defaults_registered,
    get_global_registry,
    mark_defaults_registered,
)
from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.observability.jsonl_file_observability import JSONLFileObservability
from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore
from lca.layer1_cognitive.event_bus import SimpleEventBus
from lca.layer1_cognitive.memory.simple_memory import SimpleMemorySystem
from lca.layer2_runtime.strategy_registry import get_global_strategy_registry
from lca.layer3_agent.orchestration_registry import get_global_orchestration_registry
from lca.contracts.enums import TeamProcess, CompletionPolicyName

# ── 简单组件：直接注册类，assembly 负责实例化 ──

_DEFAULT_COMPONENTS: dict[str, dict[str, type]] = {
    "observability": {"console": ConsoleObservability, "jsonl_file": JSONLFileObservability},
    "state_store": {"memory": InMemoryStateStore},
    "memory": {"simple": SimpleMemorySystem},
    "event_bus": {"simple": SimpleEventBus},
}

# ── 策略注册：只注册类或零参工厂，不 import assembly ──


def register_defaults() -> None:
    reg = get_global_registry()
    for category, implementations in _DEFAULT_COMPONENTS.items():
        for name, cls in implementations.items():
            reg.register(category, name, cls)

    # Brain 策略：注册工厂函数，但工厂内部不反向依赖 assembly
    strategy_reg = get_global_strategy_registry()
    strategy_reg.register("default", DefaultBrainFactory())

    # 编排策略：注册类或零参工厂
    orch_reg = get_global_orchestration_registry()
    orch_reg.register(TeamProcess.HIERARCHICAL, HierarchicalStrategy)
    orch_reg.register(TeamProcess.SEQUENTIAL, SequentialStrategy)
    # ... 其他策略

    mark_defaults_registered()
```

**关键变化**：`register_defaults()` 不再 import `assembly.py` 中的任何函数。循环依赖从架构上消除。

#### 1b. Brain 工厂：从函数闭包变为显式类

```python
# defaults.py 或独立的 brain_factory.py

from lca.contracts.protocols import BrainStrategy, LLMAdapter
from lca.contracts.role_team import RoleProfile


class DefaultBrainFactory:
    """默认 Brain 策略工厂。

    将 assembly.build_default_brain 的逻辑内聚到工厂类中，
    消除 defaults → assembly 的反向依赖。
    """

    def __call__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        tools_desc: str,
        *,
        action_registry: ActionRegistryProtocol | None = None,
    ) -> BrainStrategy:
        # 直接 import 具体类（这些是 L1 内部依赖，不经过 assembly）
        from lca.layer1_cognitive.brain.modular_brain import ModularBrain
        from lca.layer1_cognitive.brain.reasoner import SimpleReasoner
        from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
        from lca.layer1_cognitive.brain.critic import SimpleCritic
        from lca.layer1_cognitive.brain.candidate_evaluation_pipeline import (
            SimpleCandidateEvaluationPipeline,
        )
        from lca.layer1_cognitive.brain.prompts import load_builtin_prompt
        from lca.layer1_cognitive.prompt_manager import SimplePromptManager
        from lca.layer1_cognitive.body.action_catalog import format_allowed_actions_desc

        prompt_manager = SimplePromptManager()
        prompt_manager.register_template("react_prompt", load_builtin_prompt("react_prompt"))
        prompt_manager.register_template(
            "hierarchical_prompt", load_builtin_prompt("hierarchical_prompt")
        )

        allowed_actions_desc = ""
        if action_registry is not None:
            allowed_actions_desc = format_allowed_actions_desc(
                action_registry.allowed_action_types()
            )

        reasoner = SimpleReasoner(
            llm,
            prompt_manager,
            role_profile,
            tools_desc,
            allowed_actions_desc=allowed_actions_desc,
        )
        return ModularBrain(
            reasoner=reasoner,
            decision_parser=SimpleDecisionParser(action_registry=action_registry),
            critic=SimpleCritic(),
            evaluation_pipeline=SimpleCandidateEvaluationPipeline(),
        )
```

**为什么这样更优雅**：
- `defaults.py` 不再需要 `from lca.layer4_app.assembly import ...`
- Brain 构造逻辑从"assembly 里的函数 + defaults 里的 lambda 转发"变成"一个自包含的工厂类"
- 组合根变成纯数据流：`Config → 解析组件 → 构造对象图`

#### 1c. `assembly.py` 简化 —— 不再反向 import defaults

```python
# assembly.py —— 重构后

def assemble_base_agent(...) -> BaseAgent:
    ensure_defaults()  # 仍然需要，但 ensure_defaults 不再依赖 assembly
    reg = get_global_registry()

    # 组件解析：从注册表拿类，本地实例化
    obs_cls = reg.require("observability", observability if isinstance(observability, str) else "console")
    obs = obs_cls() if isinstance(observability, str) else observability
    # ... 同理 memory, state_store, event_bus

    # Brain：从策略注册表拿工厂，直接调用
    strategy_reg = get_global_strategy_registry()
    factory = strategy_reg.resolve(brain_strategy)
    brain = factory(llm, role_profile, tools_desc, action_registry=action_registry)

    # ... Body, Hooks, Runtime 构造不变
```

**变化**：`assemble_base_agent` 不再 `from lca.layer4_app.defaults import ...`。
它只依赖 `get_global_registry()` 和 `get_global_strategy_registry()`——这两个都是 L0/L2 的基础设施，不是 L4 的 defaults。

#### 1d. 兼容层处理

`_DEPRECATED_BUILDERS` + `__getattr__` 直接删除。这是内部框架，没有外部用户承诺。
如果确实有外部依赖，保留一个版本然后在 changelog 中标注 breaking change。

#### 依赖流向（重构后）

```
api.py → assembly.py → [L0 ComponentRegistry, L2 StrategyRegistry, L3 OrchestrationRegistry]
                     → [L1 Brain/Body 具体类]
                     → [L2 Runtime 具体类]

defaults.py → [L0/L1 具体类]  ← 不再依赖 assembly.py
            → [L2 StrategyRegistry]  ← 注册工厂类
            → [L3 OrchestrationRegistry]
```

**单向，无循环。**

---

## Phase 2：Hook Registry 关注点分离（根因 R2）

### 当前病根

`hook_registry.py`（142 行）混合三个关注点：

| 关注点 | 代码 | 层级归属 |
|--------|------|---------|
| 注册 + 触发 | `SimpleHookRegistry`（25 行） | L1 认知 |
| Span 属性提取 | `_extract_span_attributes`（48 行） | L0 基础设施（可观测性） |
| 密钥脱敏 + 截断 | `_sanitize`/`_truncate`/`_safe_repr`（20 行） | L0 基础设施（安全） |

后两者是**基础设施关注点**，放在 L1 是层级违规。

### 根治方案

```
layer0_infra/observability/
├── __init__.py
├── console_observability.py
├── jsonl_file_observability.py
├── redaction.py          ← 新：_sanitize, _truncate, _safe_repr
└── span_attributes.py    ← 新：_extract_span_attributes

layer1_cognitive/
└── hook_registry.py      ← 瘦身：只保留 SimpleHookRegistry + default_logging_hook
```

#### `redaction.py`（L0 基础设施）

```python
"""密钥脱敏与文本安全处理。"""

import re
from typing import Any

_MAX_PREVIEW_LEN = 200
_SECRET_PATTERN = re.compile(r"(sk-|api[_-]?key[_-]?|token[_-]?)[\w-]{8,}", re.IGNORECASE)


def sanitize(text: str) -> str:
    """过滤疑似密钥字符串。"""
    return _SECRET_PATTERN.sub("[REDACTED]", text)


def truncate(text: str, max_len: int = _MAX_PREVIEW_LEN) -> str:
    """截断过长文本。"""
    return text if len(text) <= max_len else text[:max_len] + "..."


def safe_repr(value: Any) -> Any:
    """结构化日志安全表示：原语透传，复杂对象 fallback repr()。"""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return repr(value)
```

#### `span_attributes.py`（L0 基础设施）

```python
"""从 hook kwargs 中提取 TraceSpan 属性。"""

from typing import Any
from lca.layer0_infra.observability.redaction import sanitize, truncate


def extract_span_attributes(event_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """提取 hook 上下文中的可观测属性，已脱敏。"""
    # ... 原 _extract_span_attributes 逻辑，调用 sanitize/truncate
```

#### `hook_registry.py`（L1 认知，瘦身后）

```python
"""SimpleHookRegistry —— 生命周期钩子注册与触发。"""

from lca.layer0_infra.observability.redaction import safe_repr
from lca.layer0_infra.observability.span_attributes import extract_span_attributes


class SimpleHookRegistry(HookRegistry):
    def __init__(self, observability: Observability) -> None:
        self._hooks: dict[str, list[Callable]] = {}
        self.observability = observability

    def register(self, event_name: str, hook: Callable) -> None:
        self._hooks.setdefault(event_name, []).append(hook)

    async def trigger(self, event_name: str, state: TypedState, **kwargs: Any) -> Any:
        span = TraceSpan(
            span_id=new_id("span"),
            trace_id=state.trace_id,
            name=f"hook.{event_name}",
            started_at=_now(),
            attributes=extract_span_attributes(event_name, kwargs),  # ← 委托给 L0
        )
        for hook in self._hooks.get(event_name, []):
            await hook(event_name, state, **kwargs)
        span.ended_at = _now()
        self.observability.emit_span(span)
```

**从 142 行 → ~40 行。** 职责纯粹：注册 + 触发。

---

## Phase 3：MAP 模块去双轨（根因 R3）

### 当前病根

`SimpleCandidateEvaluationPipeline` 把 MAP 五步内联为 `_predict`/`_score`/`_check_conflicts`/`_arbitrate`/`decompose`。
同时 `brain/map_modules/` 有独立的 Protocol 实现类。两套逻辑并存。

但实际上**不是真正的重复**——Pipeline 内联的是极简默认实现（`_score` 永远返回 1.0，`_check_conflicts` 永远返回空），而 `map_modules/` 是有真实逻辑的高级实现。

### 根治方案：Pipeline 组合 MAP 模块

让 `SimpleCandidateEvaluationPipeline` 接受可选的 MAP 模块注入，无注入时使用内联默认：

```python
class SimpleCandidateEvaluationPipeline(CandidateEvaluationPipeline):
    """默认评估管线。

    可通过构造函数注入 MAP 模块实现高级评估；
    未注入时使用内联的 trivial 实现（单候选场景）。
    """

    def __init__(
        self,
        predictor: StatePredictor | None = None,
        evaluator: StateEvaluator | None = None,
        conflict_monitor: ConflictMonitor | None = None,
        coordinator: TaskCoordinator | None = None,
        decomposer: TaskDecomposer | None = None,
    ) -> None:
        self._predictor = predictor
        self._evaluator = evaluator
        self._conflict_monitor = conflict_monitor
        self._coordinator = coordinator
        self._decomposer = decomposer

    async def decompose(self, state: TypedState) -> list[str]:
        if self._decomposer is not None:
            return await self._decomposer.decompose(state)
        return [state.task]

    async def evaluate(
        self, state: TypedState, candidates: list[StructuredDecision]
    ) -> StructuredDecision:
        # 如果有注入的模块，委托给它们
        if self._has_modules():
            return await self._evaluate_with_modules(state, candidates)
        return self._evaluate_trivial(state, candidates)

    def _has_modules(self) -> bool:
        return all([self._predictor, self._evaluator, self._coordinator])

    async def _evaluate_with_modules(self, state, candidates) -> StructuredDecision:
        predicted = [await self._predictor.predict(state, c) for c in candidates]
        scores = [await self._evaluator.evaluate(state, p) for p in predicted]
        conflicts = (
            await self._conflict_monitor.check(state, candidates) if self._conflict_monitor else []
        )
        if conflicts:
            _log.warning("conflicts_detected", conflicts=conflicts)
        return await self._coordinator.arbitrate(state, candidates, scores)

    def _evaluate_trivial(self, state, candidates) -> StructuredDecision:
        # 原内联逻辑
        ...
```

**效果**：
- `map_modules/` 不再是"设计了但没人用"的摆设
- Pipeline 和 MAP 模块变成**组合关系**而非**重复关系**
- `DebateStrategy` 和 Pipeline 可以共享同一套 MAP 实现
- 向后兼容：不传参数时行为不变

---

## Phase 4：死代码清理（根因 R4）

| 文件 | 处置 | 理由 |
|------|------|------|
| `brain/guarded_coordinator.py` | **删除** | 零引用，已被 `GuardedCandidateEvaluationPipeline` 取代 |
| `contracts/memory.py` 中的 `SkillRecord` | **删除** | 零引用，YAGNI |
| `contracts/memory.py` 中的 `KGTriple` | **删除** | 零引用，YAGNI |
| `brain/skill_router.py` | **保留但标记** | Protocol 存在、ModularBrain 有参数，但从未接通。添加模块级注释说明这是"预留扩展点"，不在默认装配中激活 |

---

## Phase 5：Protocol 治理（根因 R5）

### 当前病根

`MemorySystem` Protocol 中 `perceive` 是 `perceive_and_retrieve` 的默认别名，`update` 是 `update_multi_level` 的默认别名。两套名字共存，调用方不知道该用哪个。

### 根治方案

1. **权威 API 用短名**：`perceive` 和 `update` 作为抽象方法
2. **删除长名**：`perceive_and_retrieve` 和 `update_multi_level` 从 Protocol 中移除
3. **实现类同步更新**：`SimpleMemorySystem` 只实现 `perceive` / `update`

```python
@runtime_checkable
class MemorySystem(Protocol):
    async def perceive(self, state: TypedState) -> TypedState: ...
    async def update(
        self, state: TypedState, observation: Observation, reflection: Reflection
    ) -> None: ...
```

**为什么不留别名**：Protocol 是契约，契约不能有"随便你用哪个"的歧义。如果未来需要兼容，在实现类上加 `perceive_and_retrieve = perceive` 即可，但 Protocol 本身必须唯一。

---

## Phase 6：文件归属修正（根因 R6）

| 文件 | 当前位置 | 目标位置 | 理由 |
|------|---------|---------|------|
| `prompt_manager.py` | `layer1_cognitive/` 顶层 | `layer1_cognitive/brain/prompt_manager.py` | 唯一消费者是 `brain/reasoner.py` |
| `SharedMemoryTool` | `layer3_agent/shared_memory/` | `layer1_cognitive/shared_memory/`（与 `TeamSharedMemoryStore` 同包） | Tool 不应跨层依赖 Store |

`event_bus.py` 和 `hook_registry.py` 留在 `layer1_cognitive/` 顶层——它们确实是被 Brain 和 Body 共同使用的横切关注点，位置合理。

---

## 执行顺序与依赖

```
Phase 4（死代码）  ── 无依赖，最先做，减少后续改动面积
    ↓
Phase 5（Protocol）── 无依赖，可与 Phase 4 并行
    ↓
Phase 2（Hook 拆分）── 无依赖，可与 Phase 4/5 并行
    ↓
Phase 6（文件搬家）  ── 无依赖，纯移动 + import 更新
    ↓
Phase 3（MAP 去双轨）── 建议在 Phase 1 之后，因为 Pipeline 构造逻辑会变
    ↓
Phase 1（组合根）    ── 最后做，影响面最大，需要最仔细测试
```

**每个 Phase 独立 PR。** 不要混在一起。

---

## 验证清单

每个 Phase 完成后必须通过：

```bash
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports        # 五层架构契约
uv run mypy lca
uv run pytest
```

Phase 1 额外验证：
- `grep -r "from lca.layer4_app.assembly" lca/layer4_app/defaults.py` → 零结果
- `grep -r "from lca.layer4_app.defaults" lca/layer4_app/assembly.py` → 零结果（除了 `ensure_defaults`）
- 依赖方向：`defaults.py` 只向下依赖 L0-L3，不依赖 L4 内其他模块

---

## 不做的事

| 提议 | 决定 | 理由 |
|------|------|------|
| 引入 `AgentConfig` dataclass 替代所有 string key | **不做** | 过度设计。当前 string key + 注册表模式对框架规模足够，改成 dataclass 会增加 API 复杂度但收益有限 |
| 消灭全局注册表，改为实例传递 | **不做** | 全局注册表在这个场景下是合理的——框架需要"注册一次，到处可用"。问题不是全局状态本身，而是注册表里混了需要反向依赖的工厂。Phase 1 修了这个 |
| 给 `skill_router.py` 补装配接入 | **不做** | 没有需求驱动。预留扩展点不需要现在接通，标记清楚即可 |
| 引入 `_legacy.py` 保留兼容 | **不做** | 内部框架，直接删除。如果真有外部依赖，走 semver major bump |
