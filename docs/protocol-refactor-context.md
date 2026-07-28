# Protocol 契约层重构 — 现状全景文档

> **目的**：为重构 agent 提供充分的上下文，使其能理解项目脉络、识别问题、产出优雅方案。
> **生成日期**：2026-07-28

---

## 1. 项目架构概览

五层严格单向依赖：

```
contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent
                                                                    ↓
                                                               layer4_app（组合根，可依赖所有下层）
```

- 包管理器：uv
- 类型检查：mypy（strict 模式）
- 契约强制：import-linter（三条契约，见 §7）
- 数据模型约定：stdlib dataclass（ADR-0012）
- 日志：structlog
- 配置：pydantic-settings（仅用于环境变量注入，契约层无 pydantic）

---

## 2. contracts 层现状 — 文件清单与内容摘要

### 2.1 目录结构

```
lca/contracts/
├── __init__.py          # Facade，re-export 所有公共符号
├── action.py            # ActionHandler Protocol + ActionRegistryProtocol + ActionRegistry 具体类
├── approval.py          # HITL 审批：ApprovalRequest, ApprovalDecision
├── budget.py            # Budget 工厂函数 create_budget()
├── decision.py          # 决策数据类：ToolCall, DelegationSpec, StructuredDecision, Observation, Reflection
├── graph.py             # DAG 执行图：GraphNode, GraphEdge, ExecutionGraph + 验证逻辑
├── lifecycle.py         # 生命周期：TaskStatus 枚举, AgentCard, TeamMessage
├── memory.py            # 记忆模型：MemoryRecord, SkillRecord, KGTriple
├── observability.py     # 可观测性：TraceSpan, Event
├── protocols.py         # ⚠️ 核心大文件：33 个 Protocol 定义 + OrchestrationContext, StepOutcome
├── result.py            # Result 数据类 + 异常层次
├── role_team.py         # 角色/团队配置：RetryPolicy, CacheConfig, ToolPermissionManifest, RoleProfile, TeamConfig
├── state.py             # 核心状态：Budget, StateSnapshot, TypedState + ContextVar
└── team_progress.py     # DelegationLedgerProtocol + 钩子函数
```

**共 14 个文件（含 `__init__.py`）**

### 2.2 统计概览

| 类别 | 数量 |
|------|------|
| Protocol 类 | **36**（33 在 protocols.py，2 在 action.py，1 在 team_progress.py） |
| Dataclass 类 | **29** |
| Enum 类 | 1（TaskStatus） |
| Exception 类 | 5 |
| Type Alias | 4（NodeType, EdgeType, ConditionFn, RoleStatus） |
| 具体非 Protocol 类 | 1（ActionRegistry） |
| Hook 函数 | 2（ledger_tracking_hook, progress_injection_hook） |
| 工厂函数 | 1（create_budget） |
| ContextVar | 1（_current_delegator） |
| Pydantic 模型 | **0** |
| 跨层 import 行数 | **169** |

---

### 2.3 各文件详细定义

#### `protocols.py`（⚠️ 最重文件，33 个 Protocol）

这是整个契约层的核心枢纽，被几乎所有层 import。包含：

| Protocol | 方法签名 | 职责 |
|----------|---------|------|
| **LLM 相关** | | |
| `LLMAdapter` | `complete(prompt, **kwargs) -> str`, `stream(prompt, **kwargs) -> AsyncIterator[str]` | LLM 提供商抽象 |
| **认知策略** | | |
| `Reasoner` | `generate_candidates(state, n) -> list[str]` | 思维候选生成 |
| `DecisionParser` | `parse(raw_output, state) -> StructuredDecision` | LLM 输出解析 |
| `Critic` | `critique(state, observation) -> Reflection` | 自我反思/批评 |
| `TaskDecomposer` | `decompose(state) -> list[str]` | 任务分解 |
| `StatePredictor` | `predict(state, candidate_action) -> dict[str, Any]` | 状态预测 |
| `StateEvaluator` | `score(state, predicted_state) -> float` | 状态评分 |
| `ConflictMonitor` | `check(state, candidates) -> list[str]` | 冲突检测 |
| `TaskCoordinator` | `arbitrate(state, candidates, scores) -> StructuredDecision` | 多候选仲裁 |
| `BrainStrategy` | `think(state) -> StructuredDecision`, `reflect(state, observation) -> Reflection`, `set_team_roster(roster_desc)` | 认知策略总接口 |
| `CompletionPolicy` | `enforce(state, decision) -> StructuredDecision` | 确定性补全守卫 |
| `Synthesizer` | `synthesize(objective, candidates) -> Result` | MoA 聚合 |
| **执行层** | | |
| `Body` | `act(decision, state) -> Observation`, `bind_transport(transport)` | 动作执行 |
| `Tool` | attrs: `name`, `is_idempotent`, `default_timeout_s`; `execute(args) -> Observation`, `validate(args) -> str \| None` | 工具接口 |
| `ToolRegistry` | `register(tool)`, `get(name) -> Tool \| None` | 工具注册 |
| `SafeExecutor` | `execute(tool, args, retry_policy, cache_config) -> Observation` | 带重试/缓存的执行器 |
| `ActionHandler` | *(在 action.py 中定义)* | |
| `FallbackHandler` | `handle(decision, state, action_registry) -> Observation` | 未知 action_type 兜底 |
| **记忆** | | |
| `MemorySystem` | `perceive_and_retrieve(state) -> TypedState`, `update_multi_level(state, observation, reflection)` | 记忆管理 |
| `SharedMemoryStore` | `is_shared(layer) -> bool`, `add_record(layer, record)`, `get_records(layer) -> list[MemoryRecord]` | 跨 Agent 共享记忆 |
| **事件/Hook** | | |
| `EventBus` | `emit(event_name, payload, trace_id)`, `subscribe(event_name, handler)` | 事件发布/订阅 |
| `Hook` | `__call__(event_name, state, **kwargs)` | 生命周期钩子 |
| `HookRegistry` | `register(event_name, hook)`, `trigger(event_name, state, **kwargs) -> Any` | 钩子管理 |
| **Prompt** | | |
| `PromptManager` | `render(template_name, variables) -> str`, `register_template(name, template, version)` | Prompt 模板管理 |
| `SkillRouter` | `route(state) -> str` | 动态 Prompt/工具路由 |
| **状态持久化** | | |
| `StateStore` | `save(state) -> str`, `load(state_ref) -> TypedState` | 状态存储 |
| **Agent 通信** | | |
| `AgentTransport` | attr: `protocol_name`; `send_task(agent_card, subtask, context_refs) -> str`, `poll_status(task_id) -> str`, `receive_result(task_id) -> Observation` | Agent 间传输 |
| **运行时** | | |
| `Runtime` | `run(task, max_steps, max_wall_clock_seconds, **context) -> Result`, `configure(**capabilities)` | Agent 运行时 |
| `AgentRuntime` | `execute(task, **context) -> Result` | 单 Agent 运行时 |
| `TeamRuntime` | `run(objective) -> Result` | 团队运行时 |
| `OrchestrationStrategy` | `run(context, objective) -> Result` | 团队编排策略 |
| **注册表** | | |
| `RegistryProtocol` | `register(name, impl)`, `resolve(name) -> Any`, `list() -> list[str]`, `__contains__(name) -> bool` | 通用命名注册表 |
| `TransportRegistryProtocol` | `register(transport)`, `resolve(protocol_name) -> AgentTransport`, `list_protocols() -> list[str]` | 传输路由注册表 |
| **步骤策略** | | |
| `StepOutcomePolicy` | `resolve(state, decision, observation, reflection) -> StepOutcome`, `resolve_budget_exceeded(observation, state) -> StepOutcome` | 步骤继续策略 |

同文件还有 2 个 dataclass：
- `OrchestrationContext` — members, config, supervisor, transport, roster_desc, ledger_factory
- `StepOutcome` — should_stop, final_output, status

#### `state.py`（核心状态）
```python
@dataclass
class Budget:                    # max_tokens, max_cost_usd, max_steps, max_wall_clock_seconds,
                                 # used_tokens, used_cost_usd, used_steps, started_at, extra
                                 # 有 exceeded() 方法

@dataclass
class StateSnapshot:             # snapshot_id, step, state_ref, reason, created_at

@dataclass
class TypedState:                # trace_id, task, budget, schema_version,
                                 # working_memory, retrieved_context, step, checkpoints,
                                 # status, extra, agent_role, delegated_by, team_progress
                                 # 有 snapshot() 方法

_current_delegator: ContextVar[str]  # 异步委托传播
```

#### `decision.py`（决策数据类）
```python
@dataclass
class ToolCall:                  # call_id, tool_name, arguments, idempotency_key, timeout_s

@dataclass
class DelegationSpec:            # subtask, target_role, target_agent_id, target_agent_card,
                                 # context_refs, deadline, protocol: Literal["internal","a2a","mcp"]

@dataclass
class StructuredDecision:        # decision_id, action_type, rationale, confidence,
                                 # tool_calls, delegate_to, response_text,
                                 # schema_version, created_at, extra

@dataclass
class Observation:               # observation_id, success, payload, content_type,
                                 # tool_call_id, error, retries_used, latency_ms, extra

@dataclass
class Reflection:                # reflection_id,
                                 # verdict: Literal["on_track","needs_correction","blocked","degraded_but_completed"],
                                 # lesson, correction, extra
```

#### `result.py`（结果 + 异常）
```python
@dataclass
class Result:                    # trace_id, status: Literal["completed","failed","paused","waiting_human"],
                                 # final_state_ref, total_steps, budget_used, schema_version,
                                 # output, lessons, trace_url, error, extra
                                 # 有 failed() classmethod

# 异常层次：
class GraphValidationError(Exception)
class ApprovalPendingError(Exception)
class BudgetExceededError(Exception)
class ToolExecutionError(Exception)     # retryable: bool = True
class ToolInputError(ToolExecutionError)  # retryable = False
```

#### `action.py`（动作路由）
```python
class ActionHandler(Protocol):     # execute(decision, state) -> Observation

class ActionRegistryProtocol(Protocol):
    # register(action_type, handler), resolve(action_type) -> ActionHandler | None,
    # allowed_action_types() -> list[str], is_registered(action_type) -> bool

class ActionRegistry:              # 具体类（非 Protocol），实现了 ActionRegistryProtocol
```

#### `role_team.py`（角色/团队配置）
```python
@dataclass
class RetryPolicy:                 # max_retries=3, backoff_base_s=1.0, backoff_multiplier=2.0, retryable_errors
@dataclass
class CacheConfig:                 # enabled=True, ttl_s=300, key_fields
@dataclass
class ToolPermissionManifest:      # allowed_tools, max_calls_per_task, requires_approval
@dataclass
class RoleProfile:                 # role, goal, backstory, tool_permission_manifest, tone, values, extra
@dataclass
class TeamConfig:                  # process: Literal["hierarchical","sequential","parallel","graph","debate","handoff"],
                                   # shared_memory_layers, max_rounds, graph_definition_ref, completion_policy
```

#### `memory.py`（记忆模型）
```python
@dataclass
class MemoryRecord:                # record_id, content, memory_type: Literal["working","semantic","episodic","procedural"],
                                   # importance, recency_score, embedding, source_trace_id, ttl, metadata
@dataclass
class SkillRecord:                 # skill_id, name, description, trigger_pattern, workflow_ref,
                                   # success_rate, usage_count, last_used_at, extra
@dataclass
class KGTriple:                    # triple_id, subject, predicate, object, confidence,
                                   # source_trace_id, valid_from, valid_until
```

#### `graph.py`（DAG 执行图）
```python
NodeType = Literal["entry", "exit", "agent", "router", "aggregator"]
EdgeType = Literal["fixed", "conditional", "parallel"]
ConditionFn = Callable[[TypedState], bool]

@dataclass
class GraphNode:                   # id, type: NodeType, config
@dataclass
class GraphEdge:                   # source, target, type: EdgeType, condition
@dataclass
class ExecutionGraph:              # nodes, edges, allow_cycle
                                 # 方法: add_node(), add_edge(), outgoing(), incoming(),
                                 #        validate(), _check_acyclic(), topological_order()
```

#### `lifecycle.py`（生命周期）
```python
class TaskStatus(str, Enum):       # SUBMITTED, WORKING, INPUT_REQUIRED, COMPLETED, FAILED, CANCELED

@dataclass
class AgentCard:                   # agent_id, role, capabilities, tools_exposed,
                                   # protocols_supported, endpoint, extra
@dataclass
class TeamMessage:                 # message_id, from_agent_id, to_agent_id, task_id,
                                   # status, payload, created_at
```

#### `observability.py`（可观测性）
```python
@dataclass
class TraceSpan:                   # span_id, trace_id, name, started_at, parent_span_id,
                                   # ended_at, status, attributes
@dataclass
class Event:                       # event_id, event_name, trace_id, payload, emitted_at
```

#### `approval.py`（HITL 审批）
```python
@dataclass
class ApprovalRequest:             # request_id, trace_id, step, risk_reason,
                                   # pending_decision, created_at, extra
@dataclass
class ApprovalDecision:            # request_id, approved, approver, comment, decided_at
```

#### `budget.py`（预算工厂）
```python
def create_budget(...) -> Budget:  # 单一预算创建入口
```

#### `team_progress.py`（团队进度追踪）
```python
RoleStatus = Literal["pending", "in_progress", "done", "failed"]

class DelegationLedgerProtocol(Protocol):
    # mandatory_roles -> frozenset[str]
    # status -> dict[str, RoleStatus]
    # mark(role, new_status) -> DelegationLedgerProtocol
    # is_covered() -> bool
    # pending_roles() -> list[str]

async def ledger_tracking_hook(...)    # 钩子函数
async def progress_injection_hook(...) # 钩子函数
```

---

### 2.4 contracts 内部依赖 DAG

```
protocols.py ←── action.py（imports ActionRegistryProtocol）
            ←── decision.py（imports Observation, Reflection, StructuredDecision）
            ←── memory.py（imports MemoryRecord）
            ←── result.py（imports Result）
            ←── role_team.py（imports CacheConfig, RetryPolicy, TeamConfig）
            ←── state.py（imports TypedState）

state.py ←── team_progress.py（imports DelegationLedgerProtocol）
       ←── result.py（imports Budget）
       ←── budget.py（imports Budget）

decision.py ←── approval.py（imports StructuredDecision）
          ←── action.py（imports Observation, StructuredDecision）
          ←── state.py（imports TypedState）
          ←── graph.py（imports TypedState）
```

**`protocols.py` 是最重枢纽**，import 了 6 个其他 contracts 模块。叶子模块（无内部依赖）：`team_progress.py`, `decision.py`, `memory.py`, `observability.py`, `role_team.py`, `lifecycle.py`。

---

## 3. 各层对 contracts 的依赖分布

| 层 | import contracts 的文件数 | import 行数 | 主要消费的符号 |
|----|--------------------------|------------|---------------|
| layer0_infra | 11 | ~18 | LLMAdapter, Tool, ToolRegistry, Observability, RegistryProtocol, StateStore, AgentTransport |
| layer1_cognitive | 18 | ~45 | BrainStrategy, Body, MemorySystem, EventBus, HookRegistry, PromptManager, SkillRouter, ActionHandler |
| layer2_runtime | 5 | ~15 | Runtime, StepOutcomePolicy, FallbackHandler, Hook, HookRegistry |
| layer3_agent | 10 | ~22 | OrchestrationStrategy, TeamRuntime, AgentTransport, TransportRegistryProtocol |
| layer4_app | 2 | ~8 | 几乎所有符号（组装根） |

**被 import 最多的 contracts 模块**：
1. `protocols.py` — 几乎每层都 import
2. `state.py`（TypedState, Budget）— 每层都 import
3. `decision.py`（Observation, StructuredDecision）— 每层都 import
4. `result.py`（Result, 异常）— L1-L4
5. `role_team.py`（RoleProfile, TeamConfig, RetryPolicy, CacheConfig）— L0-L4

---

## 4. 已识别的问题

### 4.1 `protocols.py` 上帝文件问题

**33 个 Protocol 塞在一个文件里**，涵盖 LLM、认知策略、执行、记忆、事件、Prompt、状态、运行时、注册表等完全不同的领域。这是最大的结构性问题：

- 文件过长，认知负担重
- 不同领域的 Protocol 混在一起，缺乏领域边界感
- 修改任何一个 Protocol 都要在一个大文件中定位
- 与 contracts 层「读契约即理解项目脉络」的目标严重冲突

### 4.2 命名冲突 / 语义模糊

| 问题 | 详情 |
|------|------|
| **`Tool` Protocol vs `ToolCall` dataclass** | `protocols.py` 定义 `Tool` Protocol（工具接口），`decision.py` 定义 `ToolCall`（工具调用请求）。名字相近但一个是能力声明、一个是调用实例 |
| **`ActionHandler` 出现两处** | `protocols.py` 和 `action.py` 都涉及 ActionHandler，需要确认是否有重复定义 |
| **`Runtime` vs `AgentRuntime` vs `TeamRuntime`** | 三个运行时 Protocol，边界不清晰。`Runtime.configure()` vs `AgentRuntime.execute()` vs `TeamRuntime.run()` 职责重叠 |
| **`RegistryProtocol` vs `ToolRegistry` vs `ActionRegistryProtocol` vs `TransportRegistryProtocol`** | 4 种注册表 Protocol，泛化程度不同。`RegistryProtocol` 是通用的，其他三个是特化的，是否有统一的可能？ |
| **`EventBus` vs `Hook` vs `HookRegistry`** | 三套事件/钩子机制共存，边界不清 |

### 4.3 文件职责分析

| 文件 | 问题 |
|------|------|
| `protocols.py` | ⚠️ 33 个 Protocol 的上帝文件，需按领域拆分 |
| `state.py` | 混合了 Budget（资源约束）、StateSnapshot（检查点）、TypedState（运行时状态）、ContextVar（异步传播）。ContextVar 是运行时关注点，不应在纯数据契约中 |
| `graph.py` | `ExecutionGraph` 包含行为方法（validate, topological_order），这更像领域逻辑而非纯契约。按 ADR-0015 应考虑迁出 |
| `team_progress.py` | 混合了 Protocol 定义（DelegationLedgerProtocol）、类型别名（RoleStatus）、钩子函数实现。钩子函数是实现，不是契约 |
| `action.py` | 混合了 Protocol（ActionHandler, ActionRegistryProtocol）和具体类（ActionRegistry）。按 ADR-0015 具体类应迁出 |
| `result.py` | 混合了数据类（Result）和异常层次。异常应独立 |
| `budget.py` | 仅一个工厂函数，文件过于碎片 |

### 4.4 ADR 约束与违规

| ADR | 决定 | 当前状态 |
|-----|------|---------|
| ADR-0001 | 五层单向依赖 | ✅ 由 import-linter 强制执行 |
| ADR-0004 | Protocol-First 可插拔性 | ✅ 36 个 Protocol |
| ADR-0010 | 组件 Protocol 豁免规则 | ✅ L4 facade 和 DI 基础设施豁免 |
| ADR-0012 | contracts 用 stdlib dataclass | ✅ 无 pydantic |
| ADR-0015 | contracts 只含类型和接口，实现类走 L4 注入 | ⚠️ **疑似违规**：`ActionRegistry`（具体类）在 contracts 中；`ExecutionGraph` 含行为方法；`team_progress.py` 含钩子函数实现 |

### 4.5 dataclass 一致性问题

- `Budget` 有 `exceeded()` 行为方法，`TypedState` 有 `snapshot()` 方法，`ExecutionGraph` 有丰富的行为方法 — dataclass 中混入领域逻辑的程度不一致
- `TypedState` 字段很多（12+ 字段），是否应该拆分？
- `StructuredDecision` 字段也很多（10+ 字段），且 `extra: dict` 作为逃生舱
- 部分 dataclass 使用 `Literal` 类型做状态约束（如 `Reflection.verdict`），部分使用 Enum（如 `TaskStatus`），风格不统一

### 4.6 缺失的抽象

- **无 Agent Protocol**：agent 的核心接口未在 contracts 中声明
- **`SharedMemoryStore` 与 `MemorySystem` 关系不清**：两者都在记忆领域，边界是什么？

---

## 5. ADR 决策记录汇总

| ADR | 内容 | 对重构的约束 |
|-----|------|-------------|
| ADR-0001 | 五层单向依赖 | contracts 是最底层，不可反向依赖 |
| ADR-0004 | Protocol-First 可插拔性 | 所有可替换组件必须先定义 Protocol |
| ADR-0010 | 组件 Protocol 豁免规则 | L4 facade 和 DI 基础设施可豁免 |
| ADR-0012 | contracts 用 stdlib dataclass | **如要引入 pydantic 需新 ADR 覆盖** |
| ADR-0015 | contracts 只含类型和接口 | 具体实现类、钩子函数、行为逻辑应迁出 |

---

## 6. import-linter 契约配置

三条强制契约：

```toml
# 1. 严格分层（每层只能 import 直接下层）
[[tool.importlinter.contracts]]
type = "layers"
layers = [
    "lca.contracts",
    "lca.layer0_infra",
    "lca.layer1_cognitive",
    "lca.layer2_runtime",
    "lca.layer3_agent",
    "lca.layer4_app",
]

# 2. L4 组合根：L0-L3 禁止 import layer4_app
[[tool.importlinter.contracts]]
type = "forbidden"
source = ["lca.layer0_infra", "lca.layer1_cognitive", "lca.layer2_runtime", "lca.layer3_agent"],
forbidden_modules = ["lca.layer4_app"]

# 3. contracts 纯净性：禁止 import 任何 layer
[[tool.importlinter.contracts]]
type = "forbidden"
source = ["lca.contracts"],
forbidden_modules = ["lca.layer0_infra", "lca.layer1_cognitive", "lca.layer2_runtime", "lca.layer3_agent", "lca.layer4_app"]
```

**重构注意**：拆分 contracts 子模块不影响 import-linter 配置（它只检查包级别），但所有 `from lca.contracts.xxx import` 的路径需同步更新。

---

## 7. 测试结构

```
tests/
├── unit/
│   ├── contracts/           # 每个 contracts 文件有对应测试
│   ├── layer0_infra/
│   ├── layer1_cognitive/
│   ├── layer2_runtime/
│   └── layer3_agent/
├── integration/
│   ├── test_e2e_agent.py
│   ├── test_e2e_team.py
│   └── test_e2e_with_tools.py
├── fixtures/
│   └── team_scenarios/*.yaml
└── support/
    └── scenario_loader.py
```

重构时需同步更新：
- contracts 测试文件的 import 路径
- 如果 contracts 拆分为子包，测试目录也需对应调整

---

## 8. 重构目标与约束（用户要求）

1. **更清晰的层次**：按领域/关注点分组，而非技术类型
2. **目录结构优化**：子包划分合理，打开目录即能理解项目脉络
3. **边界感**：每个文件职责单一，关注点不混合
4. **契约高度独立**：contracts 层零外部依赖，纯自包含
5. **模块化**：相关概念内聚，跨域概念通过显式引用
6. **人类认知清晰**：命名一致，无歧义，读契约即是理解项目
7. **参数清晰**：字段类型、默认值、约束一目了然
8. **是否引入 pydantic**：需评估利弊，给出建议（注意 ADR-0012 约束）
9. **该清理的清理，该合并的合并**：去除冗余，合并碎片
10. **遵守 ADR-0015**：contracts 只含类型和接口，具体实现迁出

---

## 9. 重构时需要回答的关键问题

1. **`protocols.py` 如何拆分？** 33 个 Protocol 按什么维度分组？建议按领域：
   - `protocols/llm.py` — LLMAdapter
   - `protocols/cognitive.py` — BrainStrategy, Reasoner, DecisionParser, Critic, TaskDecomposer, ...
   - `protocols/execution.py` — Body, Tool, ToolRegistry, SafeExecutor, ActionHandler, FallbackHandler
   - `protocols/memory.py` — MemorySystem, SharedMemoryStore
   - `protocols/events.py` — EventBus, Hook, HookRegistry
   - `protocols/runtime.py` — Runtime, AgentRuntime, TeamRuntime, OrchestrationStrategy
   - `protocols/transport.py` — AgentTransport, TransportRegistryProtocol
   - `protocols/prompt.py` — PromptManager, SkillRouter
   - `protocols/state.py` — StateStore
   - `protocols/registry.py` — RegistryProtocol（通用）
   - `protocols/policy.py` — StepOutcomePolicy, CompletionPolicy, Synthesizer, ...
   
   还是用子包？还是保持扁平但拆文件？

2. **`protocols.py` 变成子包后，`__init__.py` 如何组织 re-export？** 保持 `from lca.contracts import BrainStrategy` 的扁平导入体验？

3. **`ActionRegistry` 具体类是否迁出？** ADR-0015 要求迁出，但它是 contracts 内部使用的简单数据结构式注册表。迁到哪里？

4. **`ExecutionGraph` 的行为方法是否迁出？** `validate()`, `topological_order()` 是领域逻辑。是否拆为 `ExecutionGraph`（纯数据）+ `GraphValidator`（逻辑）？

5. **`team_progress.py` 的钩子函数是否迁出？** `ledger_tracking_hook`, `progress_injection_hook` 是实现，不是契约。

6. **三套事件机制（`EventBus` / `Hook` + `HookRegistry`）是否统一？** 还是有意区分（领域事件 vs 生命周期钩子）？

7. **四种注册表 Protocol 是否统一为泛型 `RegistryProtocol[T]`？** 还是保持特化以保留类型安全？

8. **`state.py` 的 ContextVar 是否迁出？** `_current_delegator` 是运行时关注点。

9. **`budget.py` 是否合并到 `state.py`？** 只有一个工厂函数，独立文件过于碎片。

10. **`result.py` 的异常是否独立为 `exceptions.py`？** 当前 5 个异常类和数据类混在一起。

11. **是否引入 pydantic？** 需权衡：
    - 利：运行时校验、JSON Schema 生成、嵌套验证
    - 弊：增加运行时依赖、与 ADR-0012 冲突、性能开销
    - 折中：仅对需要运行时校验的边界模型（如 `LLMRequest`、`ToolCall`）使用 pydantic，内部状态保持 dataclass？

12. **`Literal` vs `Enum` 风格统一？** `TaskStatus` 用 Enum，`Reflection.verdict` 用 Literal，`Result.status` 用 Literal。是否统一？

13. **大字段 dataclass 是否拆分？** `TypedState`（12+ 字段）、`StructuredDecision`（10+ 字段）是否需要分解？

---

## 10. 完整文件索引

| 文件 | 路径 | 核心内容 |
|------|------|---------|
| __init__ | `lca/contracts/__init__.py` | Facade re-export |
| protocols | `lca/contracts/protocols.py` | 33 个 Protocol + 2 dataclass |
| state | `lca/contracts/state.py` | Budget, StateSnapshot, TypedState, ContextVar |
| decision | `lca/contracts/decision.py` | ToolCall, DelegationSpec, StructuredDecision, Observation, Reflection |
| result | `lca/contracts/result.py` | Result + 5 个异常类 |
| action | `lca/contracts/action.py` | ActionHandler, ActionRegistryProtocol, ActionRegistry |
| role_team | `lca/contracts/role_team.py` | RetryPolicy, CacheConfig, ToolPermissionManifest, RoleProfile, TeamConfig |
| memory | `lca/contracts/memory.py` | MemoryRecord, SkillRecord, KGTriple |
| graph | `lca/contracts/graph.py` | GraphNode, GraphEdge, ExecutionGraph + 类型别名 |
| lifecycle | `lca/contracts/lifecycle.py` | TaskStatus, AgentCard, TeamMessage |
| observability | `lca/contracts/observability.py` | TraceSpan, Event |
| approval | `lca/contracts/approval.py` | ApprovalRequest, ApprovalDecision |
| budget | `lca/contracts/budget.py` | create_budget() 工厂函数 |
| team_progress | `lca/contracts/team_progress.py` | DelegationLedgerProtocol, RoleStatus, 钩子函数 |

---

## 11. 各层实现文件与 Protocol 实现映射

### layer0_infra（基础设施实现）

| 文件 | 实现的 Protocol | 消费的 contracts 符号 |
|------|----------------|---------------------|
| `registry.py` | `NamedRegistry(RegistryProtocol)` — 泛型基类 | `RegistryProtocol` |
| `llm_adapter/mock_llm.py` | `MockLLMAdapter(LLMAdapter)` | `LLMAdapter` |
| `llm_adapter/openai_compat.py` | `OpenAICompatAdapter(LLMAdapter)` | `LLMAdapter` |
| `llm_adapter/anthropic_llm.py` | `AnthropicLLMAdapter(LLMAdapter)` | `LLMAdapter` |
| `llm_adapter/factory.py` | 工厂函数 `resolve_llm_adapter()` | `LLMAdapter` |
| `observability/console_observability.py` | `ConsoleObservability(Observability)` | `Observability`, `TraceSpan` |
| `observability/jsonl_file_observability.py` | `JSONLFileObservability(Observability)` | `Observability` |
| `state_mgmt/in_memory_store.py` | `InMemoryStateStore(StateStore)` | `StateStore`, `TypedState` |
| `tool_protocol/calculator_tool.py` | `CalculatorTool(Tool)` | `Tool`, `Observation`, `ToolInputError` |
| `tool_protocol/weather_tool.py` | `GetWeatherTool(Tool)` | `Tool`, `Observation` |
| `transport/agent_transport.py` | `InternalTransport(AgentTransport)` | `AgentTransport`, `Observation` |
| `transport/a2a_transport.py` | `A2ATransport(AgentTransport)` | `AgentTransport`, `Observation` |
| `transport/mcp_transport.py` | `MCPTransport(AgentTransport)` | `AgentTransport`, `Observation` |
| `transport/transport_registry.py` | `TransportRegistry(NamedRegistry[AgentTransport])` | `AgentTransport`, `Observation` |

### layer1_cognitive（认知策略实现）

| 文件 | 实现的 Protocol | 消费的 contracts 符号 |
|------|----------------|---------------------|
| `event_bus.py` | `SimpleEventBus(EventBus)` | `EventBus` |
| `hook_registry.py` | `SimpleHookRegistry(HookRegistry)` | `HookRegistry`, `Observability`, `TraceSpan`, `TypedState` |
| `prompt_manager.py` | `SimplePromptManager(PromptManager)` | `PromptManager` |
| `body/simple_body.py` | `SimpleBody(Body)` | `Body`, `AgentTransport`, `SafeExecutor`, `ToolRegistry`, `TransportRegistryProtocol`, `ActionRegistryProtocol`, `ActionRegistry`, `Observation`, `StructuredDecision`, `ToolExecutionError`, `TypedState` |
| `body/safe_executor.py` | `SimpleSafeExecutor(SafeExecutor)` | `SafeExecutor`, `Tool`, `Observability`, `Observation`, `TraceSpan`, `ToolExecutionError`, `RetryPolicy`, `CacheConfig`, `ToolPermissionManifest` |
| `body/tool_registry.py` | `SimpleToolRegistry(ToolRegistry)` | `Tool`, `ToolRegistry` |
| `body/action_handlers.py` | `RespondHandler`, `UseToolHandler`, `DelegateHandler`, `HandoffHandler` (all `ActionHandler`) | `ActionHandler`, `ActionRegistry`, `AgentTransport`, `SafeExecutor`, `ToolRegistry`, `TransportRegistryProtocol`, `Observation`, `StructuredDecision`, `ToolExecutionError`, `CacheConfig`, `RetryPolicy`, `TypedState`, `_current_delegator` |
| `body/fallback_decorated_body.py` | `FallbackDecoratedBody(Body)` — 装饰器 | `Body`, `AgentTransport`, `FallbackHandler`, `ActionRegistryProtocol`, `Observation`, `StructuredDecision`, `ToolExecutionError`, `TypedState` |
| `brain/reasoner.py` | `SimpleReasoner(Reasoner)` | `LLMAdapter`, `PromptManager`, `Reasoner`, `RoleProfile`, `TypedState` |
| `brain/decision_parser.py` | `SimpleDecisionParser(DecisionParser)` | `DecisionParser`, `ActionRegistryProtocol`, `DelegationSpec`, `StructuredDecision`, `ToolCall`, `TypedState` |
| `brain/critic.py` | `SimpleCritic(Critic)` | `Critic`, `Observation`, `Reflection`, `TypedState` |
| `brain/modular_brain.py` | `ModularBrain(BrainStrategy)` | `BrainStrategy`, `Reasoner`, `DecisionParser`, `Critic`, `TaskDecomposer`, `StatePredictor`, `StateEvaluator`, `ConflictMonitor`, `TaskCoordinator`, `SkillRouter`, `Observation`, `Reflection`, `StructuredDecision`, `TypedState` |
| `brain/guarded_coordinator.py` | `GuardedTaskCoordinator(TaskCoordinator)` — 装饰器 | `TaskCoordinator`, `CompletionPolicy`, `StructuredDecision`, `TypedState` |
| `brain/skill_router.py` | `KeywordSkillRouter`, `StaticSkillRouter` (`SkillRouter`) | `SkillRouter`, `TypedState` |
| `brain/synthesizer.py` | `ConcatSynthesizer(Synthesizer)` | `Synthesizer`, `Result`, `Budget` |
| `brain/map_modules/*.py` | 各自实现 MAP 子 Protocol | `TaskDecomposer`, `StatePredictor`, `StateEvaluator`, `ConflictMonitor`, `TaskCoordinator` |
| `brain/completion_policies/roster_coverage.py` | `RosterCoveragePolicy(CompletionPolicy)` | `CompletionPolicy`, `DelegationSpec`, `StructuredDecision`, `TypedState` |
| `memory/simple_memory.py` | `SimpleMemorySystem(MemorySystem)` | `MemorySystem`, `SharedMemoryStore`, `MemoryRecord`, `Observation`, `Reflection`, `TypedState` |
| `memory/team_shared_memory.py` | `TeamSharedMemoryStore(SharedMemoryStore)` | `SharedMemoryStore`, `MemoryRecord` |
| `team_progress/delegation_ledger.py` | `DelegationLedger`（结构化合约） | `RoleStatus` |

### layer2_runtime（运行时引擎）

| 文件 | 实现的 Protocol | 消费的 contracts 符号 |
|------|----------------|---------------------|
| `runtime_loop.py` | `CognitiveRuntime(Runtime)` | `Runtime`, `BrainStrategy`, `Body`, `MemorySystem`, `HookRegistry`, `StateStore`, `StepOutcomePolicy`, `StepOutcome`, `Observation`, `Reflection`, `StructuredDecision`, `Result`, `ApprovalPendingError`, `BudgetExceededError`, `StateSnapshot`, `TypedState`, `create_budget` |
| `hooks.py` | `make_event_emitting_hook()` 工厂 | `EventBus`, `TypedState` |
| `fallback_handler.py` | `FallbackActionHandler(FallbackHandler)` | `FallbackHandler`, `ActionRegistryProtocol`, `Observation`, `StructuredDecision`, `TypedState` |
| `strategy_registry.py` | `StrategyRegistry(NamedRegistry[BrainFactory])` | `BrainStrategy` |
| `outcome_policies/default_outcome_policy.py` | `DefaultStepOutcomePolicy(StepOutcomePolicy)` | `StepOutcomePolicy`, `StepOutcome`, `Observation`, `Reflection`, `StructuredDecision`, `TypedState` |

### layer3_agent（Agent 组装）

| 文件 | 实现的 Protocol | 消费的 contracts 符号 |
|------|----------------|---------------------|
| `base_agent.py` | `BaseAgent(AgentRuntime)` | `AgentRuntime`, `Runtime`, `Result`, `RoleProfile` |
| `supervisor.py` | `Supervisor(BaseAgent)` | `AgentTransport`, `Runtime`, `RoleProfile` |
| `team_orchestrator.py` | `TeamOrchestrator(TeamRuntime)` | `TeamRuntime`, `OrchestrationStrategy`, `OrchestrationContext`, `AgentTransport`, `SharedMemoryStore`, `Result`, `TeamConfig` |
| `group_chat.py` | `build_group_chat_graph()` 工厂 | `ExecutionGraph`, `GraphEdge`, `GraphNode` |
| `orchestration_registry.py` | `OrchestrationStrategyRegistry(NamedRegistry)` | `OrchestrationStrategy` |
| `orchestration_strategies/hierarchical.py` | `HierarchicalStrategy(OrchestrationStrategy)` | `OrchestrationStrategy`, `OrchestrationContext`, `Result`, `DelegationLedgerProtocol`, hooks |
| `orchestration_strategies/sequential.py` | `SequentialStrategy(OrchestrationStrategy)` | `OrchestrationStrategy`, `OrchestrationContext`, `Result` |
| `orchestration_strategies/parallel.py` | `ParallelStrategy(OrchestrationStrategy)` | `OrchestrationStrategy`, `OrchestrationContext`, `Synthesizer`, `Result` |
| `orchestration_strategies/debate.py` | `DebateStrategy(OrchestrationStrategy)` | `OrchestrationStrategy`, `OrchestrationContext`, `ConflictMonitor`, `TaskCoordinator`, `StateEvaluator`, `Result`, `Budget`, `TypedState`, `StructuredDecision` |
| `orchestration_strategies/handoff.py` | `HandoffStrategy(OrchestrationStrategy)` | `OrchestrationStrategy`, `OrchestrationContext`, `Result` |
| `orchestration_strategies/graph/strategy.py` | `GraphStrategy(OrchestrationStrategy)` | `OrchestrationStrategy`, `OrchestrationContext`, `ExecutionGraph`, `StateStore`, `Result`, `Budget`, `TypedState` |

### layer4_app（组合根）

| 文件 | 消费的 contracts 符号 |
|------|---------------------|
| `api.py` | `BrainStrategy`, `EventBus`, `LLMAdapter`, `MemorySystem`, `Observability`, `StateStore`, `TeamRuntime`, `Tool`, `Result`, `RoleProfile`, `TeamConfig`, `ToolPermissionManifest` |
| `defaults.py` | `AgentTransport`, `Body`, `BrainStrategy`, `EventBus`, `HookRegistry`, `LLMAdapter`, `MemorySystem`, `Observability`, `StateStore`, `StepOutcomePolicy`, `Tool`, `TransportRegistryProtocol`, `ActionRegistryProtocol`, `Observation`, `RoleProfile`, `ToolPermissionManifest` |

---

## 12. 架构违规与关注点

### 严格违规：无

import-linter 的三层契约（分层、L4 隔离、contracts 纯净性）在代码中**全部遵守**，无逆向依赖。

### 向下跨层依赖（允许但值得关注）

| 来源 | 目标 | 具体问题 | 建议 |
|------|------|---------|------|
| L1 `body/simple_body.py` | L0 `transport/transport_registry.py` | import 了具体类 `TransportRegistry` 而非 `TransportRegistryProtocol` | 应通过 Protocol 解耦 |
| L2 `strategy_registry.py` | L0 `registry.py` | import `NamedRegistry` 作为基类 | 基础设施复用，可接受 |
| L3 `orchestration_registry.py` | L0 `registry.py` | 同上 | 同上 |
| L3 `team_orchestrator.py` | L1 `memory/team_shared_memory.py` | import 具体类 `TeamSharedMemoryStore` 而非 `SharedMemoryStore` Protocol | 应通过 Protocol 解耦 |
| L3 `hierarchical.py` | L0 `registry.py` + L1 `guarded_coordinator.py` | import `get_global_registry` 和 `GuardedTaskCoordinator` 具体类 | 应通过 DI 注入 |

### contracts 层纯净性关注

| 问题 | ADR-0015 违规风险 |
|------|------------------|
| `ActionRegistry` 具体类在 contracts 中 | ⚠️ 已被 `test_contracts_purity.py` 显式豁免（grandfathered） |
| `ExecutionGraph` 含行为方法（validate, topological_order） | ⚠️ 领域逻辑混入纯数据契约 |
| `team_progress.py` 含钩子函数实现 | ⚠️ `ledger_tracking_hook`, `progress_injection_hook` 是函数实现，非类型声明 |

---

## 13. 设计模式清单（供重构时保持模式一致性）

| 模式 | 使用位置 | 涉及的 Protocol |
|------|---------|----------------|
| **策略模式** | 编排策略（6 种）、ActionHandler（4 种）、SkillRouter（2 种） | `OrchestrationStrategy`, `ActionHandler`, `SkillRouter` |
| **适配器模式** | LLM 提供商（3 种）、Agent 传输（3 种） | `LLMAdapter`, `AgentTransport` |
| **装饰器模式** | Body 兜底、TaskCoordinator 守卫 | `Body`（FallbackDecoratedBody）, `TaskCoordinator`（GuardedTaskCoordinator） |
| **注册表模式** | 5 种注册表（NamedRegistry 泛型基类） | `RegistryProtocol`, `ToolRegistry`, `TransportRegistryProtocol`, `ActionRegistryProtocol` |
| **责任链** | FallbackActionHandler 降级链 | `FallbackHandler` |
| **工厂模式** | LLM 选择、Budget 创建、Action 注册表构建 | `LLMAdapter`, `Budget`, `ActionRegistry` |
| **发布-订阅** | EventBus + HookRegistry | `EventBus`, `Hook`, `HookRegistry` |

---

## 14. 架构守护测试（重构时必须保持通过）

| 测试文件 | 检查内容 | 对重构的约束 |
|---------|---------|-------------|
| `test_architecture_conformance.py` | AST 扫描 L0-L3 所有类，断言每个类声明了 Protocol 基类或在豁免列表中；检查 runtime_loop 语句数 < 30 | 拆分 Protocol 文件后，实现类仍需声明 Protocol 基类 |
| `test_contracts_purity.py` | AST 扫描 contracts/，确保非 Protocol 类都是 `@dataclass` 且无自定义方法 | 重构不能引入具体类（除非显式豁免） |
| `test_layer_boundary.py` | AST 扫描 L3，确保不直接访问 `self.runtime.body` / `self.runtime.brain` | 不影响 contracts 重构 |
| `test_protocol_compliance.py` | `isinstance` 检查每个实现类是否满足其 Protocol | Protocol 签名变更需同步更新 |

---

## 15. 完整文件索引

| 文件 | 路径 | 核心内容 |
|------|------|---------|
| __init__ | `lca/contracts/__init__.py` | Facade re-export |
| protocols | `lca/contracts/protocols.py` | ⚠️ 33 个 Protocol + 2 dataclass（上帝文件） |
| state | `lca/contracts/state.py` | Budget, StateSnapshot, TypedState, ContextVar |
| decision | `lca/contracts/decision.py` | ToolCall, DelegationSpec, StructuredDecision, Observation, Reflection |
| result | `lca/contracts/result.py` | Result + 5 个异常类 |
| action | `lca/contracts/action.py` | ActionHandler, ActionRegistryProtocol, ActionRegistry（具体类） |
| role_team | `lca/contracts/role_team.py` | RetryPolicy, CacheConfig, ToolPermissionManifest, RoleProfile, TeamConfig |
| memory | `lca/contracts/memory.py` | MemoryRecord, SkillRecord, KGTriple |
| graph | `lca/contracts/graph.py` | GraphNode, GraphEdge, ExecutionGraph + 类型别名 + GraphValidationError |
| lifecycle | `lca/contracts/lifecycle.py` | TaskStatus, AgentCard, TeamMessage |
| observability | `lca/contracts/observability.py` | TraceSpan, Event |
| approval | `lca/contracts/approval.py` | ApprovalRequest, ApprovalDecision |
| budget | `lca/contracts/budget.py` | create_budget() 工厂函数 |
| team_progress | `lca/contracts/team_progress.py` | DelegationLedgerProtocol, RoleStatus, 钩子函数实现 |

---

*本文档由代码分析自动生成，所有类签名和依赖关系均来自源码实际内容。重构 agent 应结合源码验证关键细节。*
