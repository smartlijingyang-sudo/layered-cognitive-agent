# LCA Harness Spine Spec：从第一原理到可执行重构

**版本：v1.1-draft（评审修订版）**
**基于：main @ `8e552cc` 实际代码 + DSH reference architecture**
**定位：可执行的技术规格，不是愿景文档**
**修订：整合 plugin-everything 自洽性审查——Seam 统一、phase middleware、ContextVar scope 传递、Gateway 依赖边界、Phase B 详细设计**

---

## 0. 第一原理：为什么需要这次重构

### 0.1 问题的本质

LCA 当前有三个独立的事实 owner，它们在运行期各自维护状态，但没有人能保证它们一致：

| 事实 owner | 当前实现 | 问题 |
|---|---|---|
| **运行期对象图** | `AgentComposer.compose()` → `boot_capabilities()` → `new CognitiveRuntime(...)` | 每次 compose 重新构造，无 session 概念，进程重启即丢失 |
| **执行状态** | `RunSession.runnable` / `.snapshot` / `.status` | 内存持有 live handle，resume 依赖 `runnable` 引用而非 durable fact |
| **Journal 事件流** | `RunStore.append()` → projectors | 已是最可靠的事实源，但只被当作"观测"，不是驱动源 |

**根本矛盾**：Journal 已经是事实，但 Agent 的生命周期不从中派生。前端通过 `RunSession.runnable` 直接操作 Python 对象，而不是通过 command → journal → projection 的单向数据流。

### 0.2 目标不变量

重构完成后，以下不变量必须成立：

1. **N1 — Journal 唯一事实**：任何模型可见输入、工具调用、子代理报告、技能激活都有且仅有一个 durable `SessionEvent`。`AgentState`、`RunSession.status`、前端 activity 都是 journal 的 projection。
2. **N2 — Agent 是一等实体**：Agent 不等于一次 `run()` 调用。Agent = `Session + Inbox + scoped plugin tree + loop driver + AgentHandle`。进程重启后可从 journal + checkpoint 恢复。
3. **N3 — Loop 可替换**：`CognitiveRuntime` 是第一个 loop provider，不是唯一 runtime。替换 loop 不改 Gateway、不改 Session、不改 projection。
4. **N4 — Gateway 是纯 Carrier**：Gateway 只做 HTTP/SSE → typed command → projection snapshot。Gateway 不 import 任何 concrete loop、brain、body。
5. **N5 — Plugin tree 驱动装配**：生产环境通过 profile → bundles → patch 解析 plugin tree，不用 `boot_capabilities()` 硬编码。
6. **N6 — 前端消费 whole-value projection**：前端不 fold raw domain events。前端接收 `(projection_key, version, seq, whole_value)`，保持高水位 seq。

### 0.3 从 DSH 学到什么（以及什么不能照搬）

DSH 是 TypeScript + Cordis 生态。Cordis 提供 declaration merging、service tracing、fiber-scoped effect、AsyncLocalStorage-based initiator tracking 等 Python 没有的原语。

**必须吸收的结构性模式**（与语言无关）：

| 模式 | DSH 实现 | Python 对应方案 |
|---|---|---|
| Agent 是一等实体 + Handle ownership | `AgentHandle { agent, dispose() }` | 同构 dataclass + async dispose |
| AgentFactory 可替换 loop | `AgentFactory.createAgent/resume` | Protocol + registry |
| Session = append-only event log | `SessionEventMap` merge-extensible | versioned frozen dataclass registry |
| Session Projection | `ProjectionDefinition { init, apply, view }` | 同构 Protocol |
| Scoped plugin tree | Cordis `Context.fork()` with service shadow | `PluginHost` 扩展 parent delegation + `ContextVar` 传递（§3.1） |
| Single live activation | `AgentRegistry` per-id entry | 同构 |
| Command → fact → projection | Gateway submits typed commands | 同构 |
| Setup-commit-publish | 事务性 Agent 创建 | 同构 async transaction |
| **Waterfall middleware** | `waterfall('agent/pre-step', ...)` | `MiddlewareRegistry.run(seam_key, ...)` (§2.2.5, §3.8) |
| **Extension point declaration** | Cordis declaration merging | `PluginManifest.extension_points` + `DEFINITION` kind (§2.2.1) |
| **Seam completeness** | TypeScript type checking | `Loader._check_seam_completeness()` (§3.7) |
| **Fiber-scoped service tracing** | `AsyncLocalStorage` | `contextvars.ContextVar` + `ScopedPluginHost.current()` (§3.1.2) |

**不能照搬的**：

- Cordis declaration merging → Python 用显式注册表 + namespace
- TypeScript type-level session event map → Python 用 `@session_event` decorator + registry
- Cordis fiber/effect 系统 → Python 用现有 `PluginContext.effect()` + async context manager
- AsyncLocalStorage initiator tracking → Python 用 `contextvars.ContextVar`

### 0.4 终极目标：DSH 级架构自洽性

本次重构不只是解决"三个 fact owner 不一致"的当前问题，而是将 LCA 的**架构范式**从"分层认知组装"升级为 **plugin-everything 运行时**。

DSH 达到的架构自洽性（我们的北极星）：

```
系统   = kernel + 0 个 plugin           ← kernel 自身无业务逻辑
行为   = plugin₁ + plugin₂ + ...        ← 所有行为来自 plugin
配置   = profile YAML                    ← 不写代码，只组合 plugin
扩展   = 写一个 plugin                   ← 唯一的扩展方式
替换   = 换一个 plugin                   ← 唯一的替换方式
```

**自洽性检验**：任何"不走 plugin 路径的硬编码"都是架构缺陷——要么是迁移过渡期的妥协（必须有明确消除计划），要么是 spec 的遗漏。

具体地，LCA 达到自洽后：

| 当前硬编码 | 目标 |
|---|---|
| `boot_capabilities()` 硬编码 mount | Profile YAML → Loader → reconcile |
| `CognitiveRuntime` 内部 hook 硬编码调用 | Phase middleware waterfall（plugin 注册） |
| Gateway `if is_dsh_driver` 分支 | Profile/preset 选择 loop provider |
| `register_seam_catalog()` 独立校验 | Loader reconcile 的 seam-completeness pass |
| `AgentComposer.compose()` 直接 new | AgentRegistry.create() 从 plugin tree 解析 |

### 0.5 关于 "Harness" 命名

DSH 自身就叫 "DeepSeek Harness"，本 spec 沿用 `harness` 作为**内部技术术语**，表示"Agent 运行时的核心骨架层"。但在以下对外场景中避免使用：

- **产品/用户文档**：使用 "LCA Runtime" 或 "Agent Session"
- **对外 API**：`/v1/sessions/*`，不暴露 harness 概念
- **内部代码**：`lca/harness/` 包名保留，与 DSH 术语对齐，便于团队对照阅读

如果未来团队认为 `harness` 容易引起"这只是测试脚手架"的误解，可在 Phase A 稳定后统一重命名为 `runtime`。这不阻塞当前 spec 的执行。

---

## 1. 代码基线：main 分支的真实状态

### 1.1 Plugin Kernel（已实现，质量高）

**`lca/infrastructure/plugin/kernel/_host.py`** — `PluginHost`:
- 纯数据容器：`_services: dict[str, ServiceRecord]`、`events: EventBus`、`_handles: dict[str, PluginHandle]`
- `provide(handle, name, value, check)` — mount service with ownership
- `get_service(name)` — lookup without lifecycle check (delegates to lifecycle layer)
- `remove_owned_services(handle)` — cascade cleanup

**`lca/infrastructure/plugin/kernel/_context.py`** — `PluginContext`:
- Plugin-facing API：`get/require/set/mount` 服务、`effect` 可逆副作用、`on/once/emit/waterfall` 事件
- `child(key, values)` — run-scoped overlay（**关键：这是 Scope 的原型**）
- `inject(deps, callback)` — dynamic sub-fiber creation
- `accessor/mixin` — computed properties

**`lca/infrastructure/plugin/kernel/_lifecycle.py`** — `reconcile()`:
- 驱动所有 handle 收敛：LOADING → ACTIVE via dependency resolution
- Effect LIFO disposal、cascade deactivation、config rollback

**`lca/infrastructure/plugin/loader/_loader.py`** — `Loader`:
- Topological loading：validate shapes → register handles → check provides uniqueness → reconcile → check failures
- Config validation via pydantic
- Cycle detection via provides-map reachability

**`lca/infrastructure/plugin/include/`** — Profile Loader:
- YAML bundle → profile → patch 展开
- Module import → `PluginEntry` → Loader

**结论**：Plugin kernel 已经是生产可用的 Python Cordis。不需要重写，只需要扩展和接入生产。

### 1.2 Capability Boot（当前问题点）

**`lca/application/capability_boot.py`**:

```python
def boot_capabilities() -> CapabilityHub:
    register_seam_catalog()  # 注册 Definition/Provider/Consumer 三角色
    return mount_default_providers(new_capability_hub())
```

问题：
1. `AgentComposer.compose()` 每次调用 `boot_capabilities()` 创建新的 CapabilityHub 实例
2. 所有 default provider 硬编码在 `mount_default_providers()` 中
3. 没有 profile/bundle 概念——test 用 YAML profile，production 不用
4. `CapabilityHub` 是临时 object graph，不是 scoped plugin tree
5. 无法热替换、检查、卸载

### 1.3 Composer（直接构造，无间接层）

**`lca/application/composer.py`** — `AgentComposer.compose()`:
```
ctx = boot_capabilities()          # 临时 capability hub
hub = create_observability(...)     # 直接构造
mem = self._resolve_memory(...)     # 从 ctx require
state_store = self._resolve_state_store(...)
llm_rt = ctx.require(SeamKey.LLM)
brain = self._resolve_brain(...)
body = SimpleBody(...)              # 直接 new
runtime = CognitiveRuntime(brain, body, mem, hooks, state_store, stop_rule)  # 直接 new
return CognitiveAgent(runtime, profile, hub, ...)
```

问题：
1. `boot_capabilities()` 不是 profile-driven
2. `CognitiveRuntime` 直接 new，不是从 factory 解析
3. `hooks` 硬编码 journal + logging，不是 plugin 注册
4. `SimpleBody` 直接 new，tool pipeline 不可替换

### 1.4 Gateway 执行（DSH 分叉）

**`gateway/runs/execute.py`** — `execute_run()`:
```python
dsh = is_dsh_driver(session.execution_target)
if dsh:
    await execute_dsh_session(session)     # DSH 路径
else:
    if mode == SOLO_MODE_KEY:
        runnable = build_solo_agent(...)   # LCA solo 路径
    else:
        runnable = await build_runnable_team(...)  # LCA team 路径
    result = await runnable.run(question)
```

问题：
1. Gateway 知道 runtime engine（DSH vs LCA）
2. `RunSession.runnable` 持有 live Python 引用
3. resume 依赖 `session.runnable.resume()` — 进程重启不可能
4. HIL answer 通过 `session.runnable` 而非 durable command

### 1.5 Journal / RunStore（最强资产）

已有：append-only、seq 连续、frozen event、scope stamping、redaction、JSONL/SSE/OTel/Langfuse projectors、doctor。

缺失：
1. 事件词表不够丰富（缺 turn/step/context/tool-call/skill/subagent 细粒度事件）
2. 不是 Agent Session 的驱动源——只是观测
3. 没有 Projection Registry——projector 各自订阅
4. 没有 SessionHeader（parent/fork/delegationDepth/presetDigest）

### 1.6 CognitiveRuntime（成熟的认知闭环）

**`lca/runtime/runtime_loop.py`**:
```
perceive → think → act → reflect → record → checkpoint → stop
```

优势：
- 清晰的 7-phase 闭环
- Hook registry 在每 phase 前后触发
- StopPolicy 作为 State 群策略完全分离，并仅由 Stop 阶段消费
- HIL resume via `state_store.load(snapshot)`
- Loop intervention（连续相同工具检测）

这些**都必须保留**。改变的是它获取依赖和写事实的方式。

### 1.7 关键发现：两套并行扩展机制必须统一

代码审计揭示了一个架构断层：**LCA 实际有两套并行的扩展机制**，它们解决同一个问题但方式完全不同：

| 维度 | Capability Seam（`capability_boot.py`） | Plugin Kernel（`plugin/kernel/`） |
|---|---|---|
| **激活时机** | 每次 `compose()` 调用时同步执行 | Gateway boot 时一次加载，运行时 reconcile |
| **配置方式** | Python 硬编码 `mount_default_providers()` | YAML profile → bundles → patch |
| **依赖解析** | 直接 `ctx.require(SeamKey.X)` | 拓扑排序 + 迭代收敛（`reconcile()`） |
| **生命周期** | 无（临时 object graph） | 完整状态机：PENDING → LOADING → ACTIVE → DISPOSED |
| **卸载能力** | 无 | LIFO effect disposal + cascade deactivation |
| **可观测** | 无 | `PluginHandle.state`、effect count、service table |
| **使用方** | `AgentComposer`（生产路径） | `tests/plugin/`（测试路径） |

**问题本质**：Plugin kernel 是完整的 DSH Cordis Python 移植（service table + event bus 5种dispatch模式 + lifecycle state machine + YAML profile loader + cascade deactivation），但**生产代码从未真正使用它**。`boot_capabilities()` 是一个绕过 plugin kernel 的硬编码快捷路径。

同时，Capability Seam 的 `register_seam_catalog()` + `consume()` 模式有独立的价值——它是 **composition-time gate**，在组装阶段验证 Definition/Provider/Consumer 三角完整性。这个模式应该**融入** plugin kernel 而不是被替代。

**Spec 的统一策略**：

```
当前：
  boot_capabilities() → CapabilityHub（硬编码，每次 compose 新建）
  register_seam_catalog() → seam 元数据注册（仅校验，不驱动）
  Plugin kernel → 测试用，生产不用

目标：
  Plugin kernel 成为唯一运行时 → Profile → Loader → reconcile → ScopedPluginHost
  Seam 元数据融入 PluginManifest（requires/provides/kind）
  boot_capabilities() → 仅作为兼容 adapter，内部调用 Loader.load(base_spine_bundle)
  consume() → 编译期校验工具，不影响运行期
```

这解释了为什么蓝图说"plugin kernel 已存在但生产不用"——**不是因为它不好，而是因为 `boot_capabilities()` 先存在且被 Composer 直接依赖，后来加的 plugin kernel 没有机会接管**。迁移的核心工作就是让 plugin kernel 接管 boot_capabilities 的职责。

### 1.8 其他代码级发现

**Journal 事件词表已比蓝图描述的更丰富**：`journal_catalog.py` 有 26 种事件类型，每种带 `JournalSchemaMeta`（durability、audience、sensitivity、retention_class）。Spec §2.2.3 的事件词表应视为对这 26 种的**分类整理和命名统一**，不是从零开始。

**`RunStore.derive_events()` 已是 projection 原型**：它缓存 predicate → events 映射，首次全量扫描，后续增量扩展。这就是 DSH `ProjectionDefinition { init, apply, view }` 的简化版。迁移方向是将其泛化为 registry-driven 的多 projection 模型。

**`RunSession` 有请求去重**：`run_dedup_key()` 用 SHA-256 从 `(mode, agent_id, user_text, attachment_ids)` 生成指纹，合并重复请求。新 Command 模型必须保留等价的幂等机制。

**`ingress.py` 净化 LobeHub XML 污染**：`parse_messages()` 剥离 LobeHub 注入的 `<available_tools>`、`<agent_management_context>` 等 XML。这是 carrier 层关注点，新 Gateway carrier plugin 应保留此能力。

**`InsightEngine` 是 domain projection 贡献者**：它在 `TeamRunFinished`/`AgentRunFinished` 时运行 insight rules 并发射 `RunInsight` 事件回 `store.append()`。这就是 DSH Session Projection 的 domain contributor 模式。

---

## 2. 目标架构：精确接口定义

### 2.1 包结构演进

```
lca/
├── contracts/
│   ├── harness/                     # 新增：Harness SPI
│   │   ├── plugin.py                # PluginManifest、ScopeKind、CapabilityGrant
│   │   ├── session.py               # SessionEvent、SessionHeader、SessionId
│   │   ├── agent.py                 # AgentLoopFactory、AgentHandle、LiveAgent
│   │   ├── projection.py            # ProjectionDefinition、ProjectionRegistry
│   │   ├── tool_pipeline.py         # ToolProvider、GuardedPipeline、ToolDefinition
│   │   ├── subagent.py              # SubagentProvider、SubagentCapabilities
│   │   ├── skill.py                 # SkillProvider、SkillCatalog、SkillActivationPolicy
│   │   ├── middleware.py            # MiddlewareRegistry、PhaseMiddleware、MiddlewareRegistration
│   │   └── command.py               # TypedCommand、CommandReceipt、AgentRegistryFacade
│   ├── models/                      # 保留现有，逐步扩展
│   └── protocols/                   # 保留现有
├── harness/                         # 新增：Harness 核心实现
│   ├── kernel/                      # 迁入/复用 infrastructure/plugin/kernel
│   ├── profile/                     # 迁入/复用 infrastructure/plugin/include + 扩展
│   ├── session/                     # 以 RunStore 为核心的 SessionStore
│   │   ├── store.py                 # SessionStore: append/read/fork/flush
│   │   ├── inbox.py                 # Inbox: followup/steer/inject/cancel/when_idle
│   │   ├── header.py                # SessionHeader: version/id/parent/preset/digest
│   │   └── persistence/             # JSONL/SQLite/Postgres adapters
│   ├── agent/                       # AgentRegistry + AgentHandle
│   │   ├── registry.py              # AgentRegistry: create/resume/find/dispose
│   │   ├── handle.py                # AgentHandle: owner-only dispose
│   │   └── scope.py                 # AgentScope: scoped plugin tree
│   ├── projection/                  # ProjectionRegistry
│   │   ├── registry.py              # 一次订阅 journal → 驱动所有 reducer
│   │   └── checkpoint.py            # 持久化缓存 + cold read
│   ├── command/                     # Command Gateway
│   │   ├── gateway.py               # validate → authorize → append → dispatch
│   │   └── types.py                 # SessionCreate/MessageSend/Cancel/Answer/Steer
│   ├── prompt/                      # Prompt assembly service
│   ├── tools/                       # Scoped tool registry + guard pipeline
│   └── diagnostics/                 # inspect tree/agent, replay, doctor, normalizer
├── plugins/                         # 新增：一等 plugin modules
│   ├── loop_cognitive/              # CognitiveRuntime adapter
│   │   ├── __init__.py              # PluginManifest
│   │   ├── factory.py               # CognitiveLoopFactory(AgentLoopFactory)
│   │   └── adapter.py               # 薄适配：CognitiveRuntime → LiveAgent
│   ├── loop_dsh_bridge/             # DSH adapter as loop provider
│   ├── loop_replay/                 # Deterministic replay loop
│   ├── gateway_starlette/           # HTTP/SSE carrier plugin
│   ├── session_jsonl/               # JSONL persistence plugin
│   ├── projections_web/             # conversation/activity/status/skills projections
│   ├── skills_filesystem/           # Disk skill store as provider
│   ├── tool_skill/                  # skill(name) tool
│   ├── subagent_inprocess/          # In-process child agent provider
│   ├── subagent_team/               # Team composer as subagent provider
│   ├── subagent_dsh/                # DSH as subagent provider
│   ├── workflow_dag/                # 声明式 DAG workflow engine
│   ├── seam_definitions/            # 原 register_seam_catalog() 的声明式替代
│   ├── budget_policy/               # Budget check middleware plugin
│   ├── loop_intervention_policy/    # Loop intervention middleware plugin
│   └── content_filter_policy/       # Content filter middleware plugin
├── bundles/                         # first-party reusable compositions
│   ├── base-spine.yaml              # sessions + agents + tools + prompt
│   ├── python-cognitive.yaml        # loop_cognitive + brain/body/memory
│   ├── web-gateway.yaml             # gateway_starlette + projections_web
│   ├── observability.yaml           # OTel + Langfuse + JSONL projectors
│   └── dsh-bridge.yaml              # loop_dsh_bridge + subagent_dsh
├── profiles/                        # deployment & agent profiles
│   ├── web-standard.yaml            # 默认部署 profile
│   ├── solo-cognitive.yaml          # 单 agent 认知
│   ├── team-research.yaml           # 团队研究
│   └── creator.yaml                 # 开发者工具
├── presets/                         # agent presets
│   ├── researcher/profile.yaml      # extends: web-standard + plan_graph loop
│   └── coder/profile.yaml           # extends: web-standard + dsh bridge
├── infrastructure/                    # 保留，逐步 re-export 到 harness
├── cognition/                # 保留 Brain/Body/Memory 算法
├── runtime/                  # 过渡期保留 → 最终成为 loop_cognitive 实现源
├── agent/                    # 保留 Team/roles 领域资产
├── application/                      # 过渡期 facade → 最终只做 public API 兼容
└── gateway/                         # 薄 carrier → 逐步成为 gateway_starlette plugin
```

### 2.2 核心 Protocol 定义

#### 2.2.1 Plugin Manifest（扩展现有 PluginSpec）

```python
# lca/contracts/harness/plugin.py
from dataclasses import dataclass, field
from typing import Literal
from enum import Enum

class ScopeKind(Enum):
    DEPLOYMENT = "deployment"
    PROFILE = "profile"
    TEAM = "team"
    AGENT = "agent"
    SESSION = "session"

class PluginKind(Enum):
    SERVICE = "service"         # 提供核心服务（sessions, agents, tools）
    DEFINITION = "definition"   # 定义扩展点（原 Seam Definition）—— 声明一个 seam key 和契约
    PROVIDER = "provider"       # 实现某扩展点（原 Seam Provider）—— 对 DEFINITION 提供具体实现
    CONSUMER = "consumer"       # 消费服务/扩展点（原 Seam Consumer）
    BUNDLE = "bundle"           # 纯组合，无自身逻辑
    POLICY = "policy"           # 治理策略（sandbox_policy, approval_policy）

class ProviderMode(Enum):
    """single-active vs multi-provider registry"""
    SINGLE = "single"           # 一个 scope 内只能有一个 active（agent_loop, session persistence）
    REGISTRY = "registry"       # 命名注册表，多 provider 共存（llm, subagent, skills）

@dataclass(frozen=True)
class ExtensionPoint:
    """
    声明一个 plugin 暴露的扩展点。
    对应 DSH 的 waterfall/serial event name，对应 LCA 原 Seam Definition。
    
    语义：
    - 其他 plugin 可以通过注册 middleware 介入此扩展点
    - Loader reconcile 时校验：有 DEFINITION 必须有至少一个 PROVIDER（可选）和至少一个 CONSUMER
    - dispatch_mode 决定 middleware 的执行模式：
      - WATERFALL：前一个 middleware 的输出是后一个的输入，可逐层修改
      - SERIAL：所有 middleware 依次收到同一输入，不传递修改
      - AROUND：每个 middleware 包裹下一个，类似洋葱模型
    """
    seam_key: str                     # "llm" | "agent.pre_step" | "tools.pre_execute" | ...
    dispatch_mode: Literal["waterfall", "serial", "around"] = "waterfall"
    description: str = ""

@dataclass(frozen=True)
class CapabilityGrant:
    """声明插件需要的权限"""
    capability: str             # "tool.execute", "session.append", "agent.create"
    scope: ScopeKind = ScopeKind.AGENT

@dataclass(frozen=True)
class PluginManifest:
    id: str                                     # "lca.loop.cognitive"
    version: str                                # "1.0.0" (SemVer)
    api_version: str                            # "lca-harness/1"
    kind: PluginKind
    requires: tuple[str, ...] = ()              # 必需服务 key
    optional_requires: tuple[str, ...] = ()     # 可选依赖
    provides: tuple[str, ...] = ()              # 提供的服务 key
    provider_mode: ProviderMode = ProviderMode.SINGLE
    scopes: tuple[ScopeKind, ...] = (ScopeKind.PROFILE,)
    permissions: tuple[CapabilityGrant, ...] = ()
    config_model: type | None = None            # pydantic model
    reload: Literal["never", "restart_scope", "hot_safe"] = "restart_scope"
    # ── Seam 统一字段（§3.7）──
    seam_key: str | None = None                 # 该 plugin 关联的 seam key（DEFINITION/PROVIDER/CONSUMER 必填）
    extension_points: tuple[ExtensionPoint, ...] = ()  # 仅 DEFINITION kind 使用：声明暴露的扩展点
    middleware: tuple[str, ...] = ()            # 仅 PROVIDER/CONSUMER kind 使用：注册的扩展点名列表
```

**向后兼容**：现有 `PluginSpec` 通过 adapter 自动转为 `PluginManifest`：

```python
def manifest_from_spec(spec: PluginSpec, entry_id: str) -> PluginManifest:
    """旧 PluginSpec → 新 PluginManifest 的兼容适配"""
    return PluginManifest(
        id=entry_id,
        version="0.0.0-legacy",
        api_version="lca-harness/0",
        kind=PluginKind.PROVIDER,
        provides=(spec.provides,) if spec.provides else (),
        requires=spec.inject,
    )
```

#### 2.2.2 Session Event Registry

```python
# lca/contracts/harness/session.py
from dataclasses import dataclass
from typing import ClassVar

@dataclass(frozen=True)
class SessionHeader:
    """Session 元数据，在创建时写入一次，不可变"""
    version: int                         # SESSION_FORMAT_VERSION
    id: str                              # SessionId
    created_at: int                      # epoch ms
    cwd: str | None = None
    parent_session: str | None = None    # fork lineage
    seed_length: int | None = None
    origin: Literal["user", "subagent", "workflow"] | None = None
    delegation_depth: int | None = None
    agent_preset: str | None = None
    profile_digest: str | None = None    # resolved plugin tree hash

@dataclass(frozen=True)
class EventScope:
    """
    溯源元数据集合。
    将原 SessionEvent 的 7 个平铺溯源字段收归为一个子结构，
    减少高频事件的 per-event 开销，并明确哪些字段是 tracing 关注点。
    
    从 contextvars 自动填充（ScopedPluginHost.current() + OTel context）。
    """
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    causation_id: str | None = None      # 因果关系链
    run_activation_id: str | None = None
    plugin_id: str | None = None
    plugin_version: str | None = None
    scope_id: str | None = None

@dataclass(frozen=True)
class SessionEvent:
    """一条不可变的 session 事实"""
    type: str                            # "turn.started.v1"
    seq: int                             # 单调递增序号
    time: int                            # epoch ms
    data: dict                           # frozen payload
    # 身份
    session_id: str
    actor: str | None = None             # "user" | "agent" | "tool:xxx" | "subagent:xxx"
    provider: str | None = None          # 产生此事件的 provider id
    visibility: Literal["model", "audit", "internal"] = "model"
    # 溯源（自动填充，不手动传）
    scope: EventScope | None = None

# 事件注册：
_EVENT_REGISTRY: dict[str, type] = {}

def session_event(
    type_name: str,
    *,
    visibility: Literal["model", "audit", "internal"] = "model",
    redaction: type | None = None,
):
    """装饰器：注册一个 session event 类型"""
    def decorator(cls):
        cls._event_type = type_name
        cls._visibility = visibility
        cls._redaction = redaction
        _EVENT_REGISTRY[type_name] = cls
        return cls
    return decorator
```

#### 2.2.3 必需事件词表

```python
# lca/contracts/harness/events.py

# ── 接入 ──
@session_event("session.created.v1", visibility="audit")
@dataclass(frozen=True)
class SessionCreated: ...

@session_event("message.accepted.v1")
@dataclass(frozen=True)
class MessageAccepted:
    message_id: str
    role: str           # "user" | "assistant" | "system"
    content_ref: str    # ContentRef — 大内容走 ref，不内联

@session_event("attachment.committed.v1", visibility="audit")
@dataclass(frozen=True)
class AttachmentCommitted:
    attachment_id: str
    name: str
    size_bytes: int
    mime_type: str

@session_event("command.rejected.v1", visibility="audit")
@dataclass(frozen=True)
class CommandRejected:
    command_type: str
    reason: str

# ── Agent Loop ──
@session_event("turn.started.v1")
@dataclass(frozen=True)
class TurnStarted:
    turn: int

@session_event("turn.ended.v1")
@dataclass(frozen=True)
class TurnEnded:
    turn: int
    reason: str         # "completed" | "aborted" | "error" | "budget"

@session_event("step.started.v1")
@dataclass(frozen=True)
class StepStarted:
    turn: int
    step: int

@session_event("step.ended.v1")
@dataclass(frozen=True)
class StepEnded:
    turn: int
    step: int

# ── Context ──
@session_event("context.injected.v1", visibility="audit")
@dataclass(frozen=True)
class ContextInjected:
    source: str          # "skill" | "retrieval" | "subagent" | "system"
    content_ref: str
    model_visible: bool = True

@session_event("prompt.section.published.v1", visibility="audit")
@dataclass(frozen=True)
class PromptSectionPublished:
    section_key: str
    digest: str          # 内容 hash，不存全文

@session_event("tool.schema.published.v1", visibility="audit")
@dataclass(frozen=True)
class ToolSchemaPublished:
    tool_names: tuple[str, ...]
    digest: str

# ── LLM ──
@session_event("model.requested.v1", visibility="audit")
@dataclass(frozen=True)
class ModelRequested:
    turn: int
    step: int
    provider: str
    model: str

@session_event("model.completed.v1", visibility="audit")
@dataclass(frozen=True)
class ModelCompleted:
    turn: int
    step: int
    usage: dict | None = None   # {prompt_tokens, completion_tokens}

@session_event("model.failed.v1", visibility="audit")
@dataclass(frozen=True)
class ModelFailed:
    turn: int
    step: int
    error: str

# ── Tool ──
@session_event("tool.called.v1")
@dataclass(frozen=True)
class ToolCalled:
    call_id: str
    tool_name: str
    arguments_ref: str    # ContentRef
    provider_id: str | None = None

@session_event("tool.completed.v1")
@dataclass(frozen=True)
class ToolCompleted:
    call_id: str
    success: bool
    result_ref: str       # ContentRef
    error: str | None = None

@session_event("tool.approval_requested.v1")
@dataclass(frozen=True)
class ToolApprovalRequested:
    call_id: str
    approval_type: str
    description: str

@session_event("tool.approval_resolved.v1")
@dataclass(frozen=True)
class ToolApprovalResolved:
    call_id: str
    decision: str         # "approved" | "denied"

# ── Skill ──
@session_event("skill.catalog.published.v1", visibility="audit")
@dataclass(frozen=True)
class SkillCatalogPublished:
    entries: tuple[dict, ...]    # [{id, name, description, model_invocable}]
    digest: str

@session_event("skill.loaded.v1", visibility="audit")
@dataclass(frozen=True)
class SkillLoaded:
    skill_id: str
    content_ref: str

# ── Subagent ──
@session_event("subagent.started.v1", visibility="audit")
@dataclass(frozen=True)
class SubagentStarted:
    child_session_id: str
    provider: str
    parent_session_id: str
    delegation_depth: int

@session_event("subagent.reported.v1")
@dataclass(frozen=True)
class SubagentReported:
    child_session_id: str
    result_ref: str

@session_event("subagent.settled.v1", visibility="audit")
@dataclass(frozen=True)
class SubagentSettled:
    child_session_id: str
    status: str           # "completed" | "failed" | "cancelled"

# ── 治理 ──
@session_event("budget.updated.v1", visibility="audit")
@dataclass(frozen=True)
class BudgetUpdated:
    used_steps: int
    max_steps: int
    used_tokens: int | None = None
```

#### 2.2.4 Agent Loop SPI

```python
# lca/contracts/harness/agent.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class AgentLoopFactory(Protocol):
    """可替换的 agent loop 工厂"""
    async def create(
        self,
        scope: "AgentScope",
        identity: "AgentIdentity",
        options: "AgentOptions",
        *,
        resume_session: str | None = None,
    ) -> "AgentHandle": ...

@runtime_checkable
class AgentHandle(Protocol):
    """Owner-only handle：只有创建者能 dispose"""
    @property
    def agent(self) -> "LiveAgent": ...
    async def dispose(self, reason: str = "owner") -> None: ...

@runtime_checkable
class LiveAgent(Protocol):
    """受限视图：不能 dispose，只能交互"""
    @property
    def id(self) -> str: ...
    @property
    def session_id(self) -> str: ...
    @property
    def status(self) -> str: ...     # "working" | "idle" | "waiting_input" | "disposed"

    async def followup(self, message: "UserMessage") -> "MessageReceipt": ...
    async def steer(self, message: "UserMessage") -> "MessageReceipt": ...
    async def inject(self, message: "ContextMessage") -> "MessageReceipt": ...
    def cancel(self, reason: str = "user", *, keep_inbox: bool = True) -> None: ...
    async def when_idle(self) -> None: ...

@dataclass(frozen=True)
class AgentIdentity:
    session_id: str
    parent_session: str | None = None
    delegation_depth: int = 0
    origin: str | None = None

@dataclass(frozen=True)
class AgentOptions:
    provider: str | None = None       # LLM provider name
    model: str | None = None
    max_steps: int | None = None
    max_tokens: int | None = None
    tools_allow: tuple[str, ...] | None = None
    tools_deny: tuple[str, ...] | None = None
```

#### 2.2.5 扩展点注册与 Middleware 协议

```python
# lca/contracts/harness/middleware.py
from typing import Protocol, Any, Literal
from dataclasses import dataclass

@dataclass(frozen=True)
class MiddlewareRegistration:
    """
    一个 plugin 对某扩展点的 middleware 注册。
    priority 决定执行顺序：数字越小越先执行。
    """
    seam_key: str
    priority: int = 100
    plugin_id: str = ""

class PhaseMiddleware(Protocol):
    """
    可阻断的 middleware：返回 None 表示放行，返回修改后的 state 表示拦截/改写。
    对应 DSH waterfall 中间件。
    """
    async def __call__(self, phase: str, state: Any, context: "PhaseContext") -> Any: ...

class PhaseContext(Protocol):
    """middleware 执行上下文——只读视图，不能直接修改 session"""
    @property
    def session_id(self) -> str: ...
    @property
    def scope(self) -> "ScopedPluginHost": ...
    def record(self, event_data: Any) -> None:
        """向 session journal 追加事件"""
        ...

class MiddlewareRegistry(Protocol):
    """
    扩展点注册表。
    DEFINITION plugin 声明扩展点（register_point），
    PROVIDER/CONSUMER plugin 注册 middleware（register）。
    Loop 内核在 phase boundary 调用 run()。
    """
    def register_point(self, point: "ExtensionPoint") -> None: ...
    
    def register(self, registration: MiddlewareRegistration, middleware: PhaseMiddleware) -> None: ...
    
    async def run(
        self,
        seam_key: str,
        phase: str,
        state: Any,
        context: PhaseContext,
    ) -> Any:
        """
        按 priority 顺序执行所有注册的 middleware。
        - waterfall 模式：前一个输出作为后一个输入
        - serial 模式：每个 middleware 收到原始 state，结果收集后合并
        - around 模式：洋葱模型，外层包裹内层
        """
        ...
    
    def has_point(self, seam_key: str) -> bool: ...
    
    def list_registrations(self, seam_key: str) -> list[MiddlewareRegistration]: ...
```

**认知循环扩展点预定义**（由 `loop_cognitive` DEFINITION plugin 声明）：

| seam_key | dispatch_mode | 触发时机 | 输入类型 |
|---|---|---|---|
| `agent.before_perceive` | waterfall | perceive 之前 | `AgentState` |
| `agent.after_perceive` | waterfall | perceive 之后 | `AgentState` |
| `agent.before_think` | waterfall | think 之前 | `AgentState` |
| `agent.after_think` | waterfall | think 之后 | `AgentState` |
| `agent.before_act` | waterfall | act 之前（可拦截决策） | `AgentState` |
| `agent.after_act` | waterfall | act 之后 | `AgentState` |
| `agent.before_reflect` | waterfall | reflect 之前 | `AgentState` |
| `agent.after_reflect` | waterfall | reflect 之后 | `AgentState` |
| `agent.before_turn_end` | serial | turn 结束前最后机会 | `AgentState` |
| `agent.pre_step` | waterfall | 每个 step 开始前 | `StepInput` |
| `agent.request` | waterfall | LLM 请求构建后、发送前 | `LLMRequest` |
| `agent.request_error` | waterfall | LLM 请求失败时 | `RequestError` |

**工具管道扩展点**（由 `tools_service` DEFINITION plugin 声明）：

| seam_key | dispatch_mode | 触发时机 |
|---|---|---|
| `tools.pre_execute` | waterfall | 工具执行前（allow/deny/ask） |
| `tools.execute` | around | 工具执行（around-dispatch） |
| `tools.post_execute` | waterfall | 工具执行后（accept/block/replace） |

#### 2.2.6 Session Projection SPI

```python
# lca/contracts/harness/projection.py
from typing import Protocol, TypeVar, Generic, Any

StateT = TypeVar("StateT")
ViewT = TypeVar("ViewT")

class ProjectionDefinition(Protocol[StateT, ViewT]):
    """纯函数 reducer：init → apply(event) → view"""
    key: str
    version: int                          # state version — bump on format change

    def init(self) -> StateT: ...
    def apply(self, state: StateT, event: "StampedEvent") -> StateT: ...
    def view(self, state: StateT) -> ViewT: ...
    def validate_view(self, value: ViewT) -> bool: ...

@dataclass(frozen=True)
class ProjectionSnapshot:
    as_of_seq: int                        # 共享水位线
    values: dict[str, Any]                # key → whole value

@dataclass(frozen=True)
class ProjectionChange:
    session_id: str
    key: str
    version: int
    seq: int                              # 该 projection 的水位
    value: Any                            # whole value

class ProjectionRegistry(Protocol):
    def register(self, definition: ProjectionDefinition) -> Any: ...
    def snapshot(self, session_id: str) -> ProjectionSnapshot: ...
    def subscribe_changes(self, listener: Callable[[ProjectionChange], None]) -> Any: ...
```

#### 2.2.7 Command SPI

```python
# lca/contracts/harness/command.py
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class CommandReceipt:
    command_id: str
    session_id: str
    seq: int                              # 写入 journal 的 seq
    accepted: bool
    rejection_reason: str | None = None

# 所有 command 都是 frozen dataclass，带 idempotency key
@dataclass(frozen=True)
class SessionCreateCommand:
    idempotency_key: str
    profile: str
    preset: str | None = None
    agent_options: dict | None = None

@dataclass(frozen=True)
class MessageSendCommand:
    idempotency_key: str
    session_id: str
    role: Literal["user"]
    content: str
    attachments: tuple[str, ...] = ()

@dataclass(frozen=True)
class CancelCommand:
    session_id: str
    keep_inbox: bool = True

@dataclass(frozen=True)
class AnswerCommand:
    """HIL answer"""
    session_id: str
    answer: str

@dataclass(frozen=True)
class SteerCommand:
    session_id: str
    content: str

@dataclass(frozen=True)
class InjectCommand:
    """模型可见但不唤醒的上下文注入"""
    session_id: str
    source: str
    content: str
```

#### 2.2.8 Subagent SPI

```python
# lca/contracts/harness/subagent.py
from dataclasses import dataclass, field
from typing import Protocol

@dataclass(frozen=True)
class SubagentCapabilities:
    """描述一个 subagent provider 能做什么"""
    supports_output_schema: bool = False
    supports_tool_filter: bool = False
    supports_persona: bool = False
    supports_continuation: bool = False
    max_delegation_depth: int = 0
    supported_providers: tuple[str, ...] = ()    # "inprocess", "a2a", "dsh"

class SubagentProvider(Protocol):
    name: str
    capabilities: SubagentCapabilities

    async def start(self, request: "SubagentRequest") -> "SubagentRun": ...

class SubagentRun(Protocol):
    child_session_id: str | None
    result: Any                    # Awaitable[SubagentResult]
    def cancel(self, reason: str = "") -> None: ...
    async def dispose(self) -> None: ...
```

---

## 3. 关键机制设计

### 3.1 Scope：从 PluginContext.child() 到 ScopedPluginHost

#### 3.1.1 与现有 PluginHost 的关系

**不新建平行类，而是扩展 PluginHost**。现有 `PluginHost` 已经具备 service table、event bus、handle table、lifecycle state machine。`ScopedPluginHost` 是 `PluginHost` 的**超集**，增加三个能力：

1. **parent delegation**：resolve 时先查自身 service table，miss 则查 parent
2. **drain 语义**：child scope 必须先 drain 完毕，parent 才能 unload
3. **async 传递**：scope 通过 `contextvars.ContextVar` 在 async task 链中自动传递

这意味着 `PluginHost` 可以被视为 `parent=None` 的 `ScopedPluginHost`。现有 `PluginContext.child()` 的实现自然升级为返回 `ScopedPluginHost`。

#### 3.1.2 ScopedPluginHost 完整定义

```python
# lca/harness/kernel/scope.py
import contextvars

# ── Async scope 传递（Python 等价于 DSH 的 AsyncLocalStorage + fiber-scoped tracing）──
_current_scope: contextvars.ContextVar["ScopedPluginHost | None"] = contextvars.ContextVar(
    "plugin_scope", default=None
)

class ScopedPluginHost:
    """
    带独立 handle table、effect stack、provider realm 的 scoped plugin host。
    层级：Deployment → Profile → Team → Agent → Session/Run

    约束：
    - child scope 只能 shadow allowlisted services
    - child 不能向 parent publish
    - 父 scope unload 前 child 必须 drain
    - plugin unload 自动 cancel/wait 它拥有的 Agent/Workflow handles
    
    与 PluginHost 的关系：
    - PluginHost 是 parent=None 的 ScopedPluginHost
    - 现有 PluginContext.child() 升级为返回 ScopedPluginHost
    - PluginHost 不需要被删除或重写，只需增加 parent 参数和 resolve delegation
    """
    def __init__(self, parent: "ScopedPluginHost | None", scope_kind: ScopeKind, scope_id: str):
        self._parent = parent
        self._kind = scope_kind
        self._id = scope_id
        self._services: dict[str, ServiceRecord] = {}
        self._handles: dict[str, PluginHandle] = {}
        self._events = EventBus()
        self._children: list[ScopedPluginHost] = []
        self._middleware_registry = MiddlewareRegistry()  # §2.2.5 扩展点

    def resolve(self, service_key: str) -> Any:
        """层级解析：先查自己，再查 parent（DSH 的 nearest-layer-wins）"""
        record = self._services.get(service_key)
        if record is not None and record.available:
            return record.value
        if self._parent is not None:
            return self._parent.resolve(service_key)
        raise ServiceNotFound(service_key)

    def mount(self, handle: PluginHandle, key: str, value: Any) -> Cleanup:
        """在当前 scope mount 服务"""
        ...

    def fork(self, scope_kind: ScopeKind, scope_id: str) -> "ScopedPluginHost":
        """创建 child scope"""
        child = ScopedPluginHost(self, scope_kind, scope_id)
        self._children.append(child)
        return child

    async def run_in_scope(self, coro: Any) -> Any:
        """
        在 async task 中自动传递 scope —— Python 等价于 DSH 的 fiber-scoped Context。
        
        用法：
            scope = parent_scope.fork(ScopeKind.SESSION, session_id)
            await scope.run_in_scope(agent_loop.run())
            # 在 agent_loop.run() 内部任何地方：
            #   ScopedPluginHost.current().resolve("llm")  # 自动拿到当前 scope
        
        实现：
            contextvars.ContextVar 在 asyncio.create_task 时自动拷贝当前 context。
            run_in_scope 在进入时 set，退出时 reset。子 task 自动继承。
        """
        token = _current_scope.set(self)
        try:
            return await coro
        finally:
            _current_scope.reset(token)

    @staticmethod
    def current() -> "ScopedPluginHost":
        """获取当前 async 上下文的 scope——任何 plugin 代码无需显式传递即可访问"""
        scope = _current_scope.get()
        if scope is None:
            raise RuntimeError(
                "No active plugin scope. "
                "Use scope.run_in_scope(coro) to enter a scope context."
            )
        return scope

    async def drain(self) -> None:
        """等待所有 child drain，然后 LIFO dispose 所有 effects"""
        for child in self._children:
            await child.drain()
        # LIFO effect disposal
        ...

    @property
    def middleware(self) -> MiddlewareRegistry:
        """当前 scope 的 middleware 注册表"""
        return self._middleware_registry
```

#### 3.1.3 scope 传递示例

```python
# 创建 session scope 并运行 agent loop
deployment_scope = ScopedPluginHost(None, ScopeKind.DEPLOYMENT, "deploy-1")
profile_scope = deployment_scope.fork(ScopeKind.PROFILE, "web-standard")
agent_scope = profile_scope.fork(ScopeKind.AGENT, session_id)

# agent loop 内部可以透明获取 scope
await agent_scope.run_in_scope(
    live_agent.followup(user_message)
)

# 在 live_agent 内部（或在任何 plugin 代码中）：
async def followup(self, message):
    scope = ScopedPluginHost.current()  # 无需参数传递
    llm = scope.resolve("llm")         # 自动走 parent delegation
    middleware = scope.middleware        # 当前 scope 的 middleware 注册表
    ...

# 子 agent 自动继承 parent scope（asyncio.create_task 拷贝 ContextVar）
async def spawn_child(self):
    child_scope = ScopedPluginHost.current().fork(ScopeKind.AGENT, child_session_id)
    await child_scope.run_in_scope(child_agent.run())
```

### 3.2 Session Store：RunStore 升格

```python
# lca/harness/session/store.py
class SessionStore:
    """
    Append-only session journal — 唯一事实来源。

    从 RunStore 演进：
    - 增加 SessionHeader（创建时写入一次）
    - 增加事件词表注册（@session_event decorator）
    - 增加 scope stamping（session_id + run_activation_id + trace_id）
    - 增加 content ref（大内容走引用，不内联）
    - 保持 seq 连续、event immutable、append-before-observe
    - 保持现有 projector 接口兼容
    """
    def __init__(self, persistence: SessionPersistence, header: SessionHeader):
        self._persistence = persistence
        self._header = header
        self._seq = -1
        self._events: list[SessionEvent] = []
        self._projectors: list[JournalProjector] = []

    async def append(self, event_data: SessionEventData, *,
                     actor: str | None = None,
                     causation_id: str | None = None,
                     visibility: str = "model") -> SessionEvent:
        """追加一条事实。seq 自动分配，scope 自动 stamping"""
        self._seq += 1
        event = SessionEvent(
            type=event_data._event_type,
            seq=self._seq,
            time=now_ms(),
            data=asdict(event_data),
            session_id=self._header.id,
            actor=actor,
            causation_id=causation_id,
            visibility=visibility,
            # trace/span 从 contextvars 获取
            **_scope_from_context(),
        )
        # freeze
        self._events.append(event)
        await self._persistence.write(event)
        # notify projectors
        for proj in self._projectors:
            proj.on_event(event)
        return event

    async def read_from(self, seq: int = 0) -> list[SessionEvent]:
        """从指定 seq 开始读取"""
        ...

    @property
    def header(self) -> SessionHeader: ...

    @property
    def current_seq(self) -> int: ...
```

### 3.3 Agent Registry：create/resume/dispose 事务

```python
# lca/harness/agent/registry.py
class AgentRegistry:
    """
    Agent 生命周期管理。核心约束：
    - 一个 session_id 最多一个 live agent
    - create/resume 是事务：setup 失败 → 不 publish
    - dispose 等待 loop quiescence
    - get() 返回 LiveAgent（不能 dispose）
    - 只有 handle owner 能 dispose
    """
    def __init__(self, session_store_factory, loop_factory_registry, scope_root):
        self._live: dict[str, _AgentEntry] = {}
        self._session_store_factory = session_store_factory
        self._loop_factories = loop_factory_registry
        self._scope_root = scope_root

    async def create(
        self,
        profile: str,
        preset: str | None = None,
        *,
        session_id: str | None = None,
        parent_session: str | None = None,
        options: AgentOptions | None = None,
        setup: AgentSetup | None = None,
    ) -> AgentHandle:
        """
        事务性创建：
        1. 分配 session_id
        2. 解析 profile → plugin tree → AgentScope
        3. 创建 SessionStore + SessionHeader
        4. 解析 agent_loop factory（从 profile/preset）
        5. 运行 setup（可选）
        6. 创建 AgentHandle
        7. 注册到 _live
        8. 发射 session.created + agent.created
        9. 启动 loop

        任何步骤失败 → 回滚 scope、清理 session、不 publish
        """
        ...

    async def resume(self, session_id: str) -> AgentHandle:
        """从持久化恢复：加载 header + journal → 重建 scope → 恢复 loop"""
        ...

    def get(self, session_id: str) -> LiveAgent | None:
        """受限视图"""
        entry = self._live.get(session_id)
        return entry.live_agent if entry else None

    async def dispose(self, session_id: str, reason: str = "owner") -> None:
        """只有 handle owner 能调用"""
        ...
```

### 3.4 Gateway 作为 Command Carrier

#### 3.4.1 Contract 依赖边界

Gateway 作为 carrier plugin，其 import 边界必须严格限制：

```
Gateway 只 import：
  contracts/harness/command.py    — typed command + CommandReceipt
  contracts/harness/projection.py — ProjectionSnapshot + ProjectionChange
  contracts/harness/session.py    — SessionEvent（只用于 SSE 流）

Gateway 不 import：
  contracts/harness/agent.py      — LiveAgent, AgentHandle（封装在 AgentRegistry 内）
  cognition/*              — Brain, Body, Memory
  runtime/*                — CognitiveRuntime
  agent/*                  — CognitiveAgent, Team

消息传递：
  Gateway → AgentRegistry: 通过 session_id + content，不通过 LiveAgent
  AgentRegistry → Gateway: 通过 CommandReceipt + ProjectionChange
```

```python
# lca/harness/command/gateway.py
class CommandGateway:
    """
    职责：
    - HTTP/SSE carrier
    - schema 验证、auth、限流
    - 将请求转为 typed command
    - append accepted/rejected fact
    - 返回 projection snapshot/change

    不做：
    - 不 new Agent
    - 不选 Brain/Body/Loop
    - 不维护 agent 状态机
    - 不 import LiveAgent / AgentHandle / 任何 concrete loop

    Contract 依赖（只读）：
    - command.py: SessionCreateCommand, MessageSendCommand, CancelCommand, AnswerCommand, SteerCommand, InjectCommand, CommandReceipt
    - projection.py: ProjectionSnapshot, ProjectionChange
    - session.py: SessionEvent
    """
    def __init__(self, agent_registry: "AgentRegistryFacade", projection_registry: "ProjectionRegistry"):
        """
        注意：agent_registry 参数类型是 AgentRegistryFacade，不是 AgentRegistry。
        Facade 只暴露 dispatch/get_status 方法，不暴露 get()/LiveAgent。
        Gateway 永远拿不到 LiveAgent 引用。
        """
        self._agent_registry = agent_registry
        self._projection_registry = projection_registry

    async def handle_create_session(self, cmd: SessionCreateCommand) -> CommandReceipt:
        # validate → authorize → dispatch to registry
        receipt = await self._agent_registry.create_session(
            idempotency_key=cmd.idempotency_key,
            profile=cmd.profile,
            preset=cmd.preset,
            options=cmd.agent_options,
        )
        return receipt

    async def handle_send_message(self, cmd: MessageSendCommand) -> CommandReceipt:
        # validate → dispatch to registry（registry 内部找到 agent 并 followup）
        receipt = await self._agent_registry.dispatch_message(
            session_id=cmd.session_id,
            idempotency_key=cmd.idempotency_key,
            content=cmd.content,
            role=cmd.role,
        )
        return receipt

    async def handle_cancel(self, cmd: CancelCommand) -> CommandReceipt:
        receipt = await self._agent_registry.cancel(
            session_id=cmd.session_id,
            keep_inbox=cmd.keep_inbox,
        )
        return receipt

    async def handle_answer(self, cmd: AnswerCommand) -> CommandReceipt:
        receipt = await self._agent_registry.answer(
            session_id=cmd.session_id,
            answer=cmd.answer,
        )
        return receipt

    async def get_snapshot(self, session_id: str, as_of_seq: int = -1) -> ProjectionSnapshot:
        return self._projection_registry.snapshot(session_id)

    async def subscribe_changes(self, session_id: str, last_seq: int) -> AsyncIterator[ProjectionChange]:
        # SSE stream
        ...
```

#### 3.4.2 AgentRegistryFacade

```python
# lca/contracts/harness/command.py（或独立 facade 文件）
class AgentRegistryFacade(Protocol):
    """
    Gateway 看到的 AgentRegistry 视图。
    只暴露 command-level 操作，不暴露 LiveAgent。
    这是确保 Gateway 是纯 Carrier 的关键约束。
    """
    async def create_session(self, *, idempotency_key: str, profile: str,
                             preset: str | None, options: dict | None) -> CommandReceipt: ...
    async def dispatch_message(self, *, session_id: str, idempotency_key: str,
                               content: str, role: str) -> CommandReceipt: ...
    async def cancel(self, *, session_id: str, keep_inbox: bool) -> CommandReceipt: ...
    async def answer(self, *, session_id: str, answer: str) -> CommandReceipt: ...
    async def steer(self, *, session_id: str, content: str) -> CommandReceipt: ...
    async def inject(self, *, session_id: str, source: str, content: str) -> CommandReceipt: ...
```

**架构检验**：
- `lca/harness/command/gateway.py` 的 import 列表中不应出现 `agent.py`、`layer1_*`、`layer2_*`、`layer3_*`
- 此检验可通过 `tests/test_architecture_gateway.py` 自动化守卫

### 3.5 Cognitive Loop Provider（薄适配）

```python
# lca/plugins/loop_cognitive/factory.py
class CognitiveLoopFactory:
    """
    将现有 CognitiveRuntime 包装为 AgentLoopFactory。
    不重写认知算法——只是适配。
    """
    def __init__(self, brain_factory, body_factory, memory_factory,
                 state_store_factory, hook_registry):
        ...

    async def create(self, scope, identity, options, *, resume_session=None):
        # 1. 从 scope 解析 Brain、Body、Memory、StateStore 与 State 群 StopPolicy
        brain = scope.resolve("brain")
        body = scope.resolve("body")
        memory = scope.resolve("memory")
        state_store = scope.resolve("state_store")
        stop_policy = scope.resolve("stop_policy")

        # 2. 由 Profile 选择的 runtime factory 构造运行时；StopPolicy
        #    仅位于 Stop 阶段的局部 phase_capabilities。
        hooks = self._build_hooks(scope)
        runtime = self._runtime_factory.create(
            brain=brain,
            body=body,
            memory=memory,
            hooks=hooks,
            state_store=state_store,
            phase_capabilities={"stop_policy": stop_policy},
        )

        # 3. 包装为 LiveAgent
        live = CognitiveLiveAgent(
            runtime=runtime,
            identity=identity,
            scope=scope,
            session_store=scope.resolve("sessions"),
        )

        # 4. 如果有 resume_session，从 journal 恢复 state
        if resume_session:
            await live._restore_from_journal(resume_session)

        return CognitiveAgentHandle(agent=live, scope=scope)
```

### 3.6 DSH 深度分析补充：必须精确移植的模式

> 以下来自 DSH 源码逐行分析（packages/core/agent、core/session、core/agent-loop、core/tools、session/session-projection），是对上述设计的关键精度补充。

#### 3.6.1 Inbox 双队列模型

DSH 的 Inbox 不是一个列表，是**两个**：

```
Inbox
├── next-turn:  UserMessage[]    # followup 消息，开启新 turn
└── next-step:  UserMessage[]    # steer/inject 消息，在下一个 step 边界消费
```

**每次变更都是 durable 事实** — append、prepend、splice、claim、clear 都通过 `session.append('agent/inbox/spliced', ...)` 写入 journal。Resume 时从 session log 重建 inbox。

Python 对应：

```python
@dataclass
class InboxState:
    next_turn: list[UserMessage]     # followup → 新 turn
    next_step: list[UserMessage]     # steer/inject → 下一个 step 边界消费

class Inbox:
    """Durable FIFO projection over agent/inbox/spliced events"""
    async def followup(self, msg: UserMessage) -> None:
        """添加下一 turn 消息，唤醒 agent"""
        await self._session.append(InboxSpliced(
            op="append", target="next_turn", messages=(msg,)
        ))
        self._wake_driver()

    async def steer(self, msg: UserMessage) -> None:
        """添加 step 边界干预，唤醒 agent"""
        await self._session.append(InboxSpliced(
            op="append", target="next_step", messages=(msg,)
        ))
        self._wake_driver()

    async def inject(self, msg: UserMessage) -> None:
        """添加上下文但不唤醒"""
        await self._session.append(InboxSpliced(
            op="append", target="next_step", messages=(msg,)
        ))
        # 不唤醒 driver

    def claim_next_turn(self) -> list[UserMessage] | None:
        """Claim next-turn messages for a new turn"""
        if not self._state.next_turn:
            return None
        msgs = list(self._state.next_turn)
        self._state.next_turn.clear()
        return msgs

    def claim_next_step(self) -> list[UserMessage] | None:
        """Claim next-step messages at step boundary"""
        if not self._state.next_step:
            return None
        msgs = list(self._state.next_step)
        self._state.next_step.clear()
        return msgs
```

#### 3.6.2 Surface：模型可见的有序事件子集

DSH 的 Session 有一个 **Surface** — 只有三种事件类型可以出现在模型可见表面：

| Surface 事件类型 | 含义 |
|---|---|
| `user/message` | 用户输入 / inject 的上下文 / skill body |
| `assistant/message` | 模型完整输出（非流式 chunk） |
| `tool/result` | 工具执行结果 |

其他事件（`turn/start`、`tool/call`、`assistant/chunk`）是 log-only，不出现在 Surface。

两种 Surface 操作：
- `'append'` — 正常追加到末尾
- `{ op: 'replace', start, end }` — 位置替换（compaction 用）

Python 对应：

```python
SURFACE_EVENT_TYPES = frozenset({"user/message", "assistant/message", "tool/result"})

class SurfaceManager:
    """跟踪模型可见的有序消息表面"""
    def __init__(self):
        self._nodes: list[SessionEvent] = []

    def apply(self, event: SessionEvent) -> None:
        if event.type not in SURFACE_EVENT_TYPES:
            return
        surface_op = event.data.get("surface_op", "append")
        if surface_op == "append":
            self._nodes.append(event)
        elif isinstance(surface_op, dict) and surface_op["op"] == "replace":
            start, end = surface_op["start"], surface_op["end"]
            self._nodes[start:end+1] = [event]

    def model_messages(self) -> list[dict]:
        """生成模型可见的消息列表"""
        messages = []
        for event in self._nodes:
            if event.type == "user/message":
                messages.append({"role": "user", "content": event.data["content"]})
            elif event.type == "assistant/message":
                messages.append({"role": "assistant", "content": event.data["content"]})
            elif event.type == "tool/result":
                messages.append({"role": "tool", **event.data["message"]})
        return messages
```

#### 3.6.3 Waterfall 中间件扩展点

DSH 的扩展点是命名 waterfall/serial 事件，不是 callback list。关键 waterfall：

| 事件 | 模式 | 用途 | Python 对应 |
|---|---|---|---|
| `agent/pre-step` | waterfall | 拒绝/重写进入 step 的消息 | `AgentEventMiddleware.before_step()` |
| `agent/request` | waterfall | 替换 LLM 请求配置 | `AgentEventMiddleware.before_request()` |
| `agent/request-error` | waterfall | 自定义重试/恢复 | `AgentEventMiddleware.on_request_error()` |
| `agent/turn-stopping` | serial | 最后机会添加 steering | `AgentEventMiddleware.before_turn_end()` |
| `tools/pre-execute` | waterfall | allow/deny/ask 审批 | `ToolPipeline.pre_execute()` |
| `tools/execute` | waterfall | around-dispatch | `ToolPipeline.around_execute()` |
| `tools/post-execute` | waterfall | accept/block/replace/add context | `ToolPipeline.post_execute()` |

#### 3.6.4 工具调度：并行 vs 独占

DSH 的工具调度器：
- **exclusive tools** 形成 barrier，一次只运行一个
- **parallel tools** 有界滚动池 (`max_parallel_tool_calls`)
- 结果按**模型顺序**提交，不论实际执行顺序
- abort 时 drain 已启动的调用，为跳过的生成合成错误结果

#### 3.6.5 Two-Phase Publication：enter → announce

DSH 的 Agent 注册分两步，允许 setup 失败时回滚：

```
enter(agent) → setup → commit → announce(agent)
                 ↓ fail
              detach() (rollback, 不发射 agent.created)
```

Python 对应已在 3.3 节 AgentRegistry 中体现：setup 失败 → scope drain → 不 publish。

#### 3.6.6 ScopedLayers：层级注册解析

```
ScopedLayers
├── Global Layer      # 部署级工具（全局可见）
├── Per-Preset Layer  # preset 级（该 preset 的 agent 可见）
└── Per-Agent Layer   # agent 级（只该 agent 可见）
```

解析规则：nearest layer wins、rank-based dedup、allow/deny intersection。

### 3.7 Seam 统一：从独立注册表到 Loader reconcile pass

#### 3.7.1 问题

当前 LCA 有两套并行扩展机制：

```
独立机制 A：Seam Catalog
  register_seam(Definition, key, DEFINITION)
  register_seam(Provider, key, PROVIDER)
  register_seam(Consumer, key, CONSUMER)
  require_complete(*keys)  ← 三角完整性校验

独立机制 B：Plugin Kernel
  PluginHandle → service table → lifecycle reconcile
  不感知 Seam 三角关系
```

两套机制解决同一问题（"谁提供什么、谁消费什么、是否完整"），但互相不知道对方的存在。

#### 3.7.2 统一方案：Seam 成为 Loader 的校验 pass

**不删除 Seam，而是将其语义融入 PluginManifest + Loader reconcile**：

```python
# 统一后的 Loader.reconcile()
class Loader:
    async def reconcile(self, handles: list[PluginHandle]) -> ReconcileResult:
        # Phase 1: 依赖解析（现有逻辑）
        resolved = await self._resolve_dependencies(handles)
        
        # Phase 2: lifecycle 推进（现有逻辑）
        await self._advance_lifecycle(resolved)
        
        # Phase 3: Seam 完整性校验（新增）
        await self._check_seam_completeness(resolved)
        
        # Phase 4: Extension point 校验（新增）
        await self._check_extension_points(resolved)
        
        return ReconcileResult(resolved)
    
    async def _check_seam_completeness(self, handles: list[PluginHandle]) -> None:
        """
        收集所有 DEFINITION / PROVIDER / CONSUMER plugin 的 seam_key，
        校验每个 seam 的三角完整性。
        
        规则：
        - 每个 DEFINITION（扩展点定义）必须有至少一个 PROVIDER（实现）
          （exception: optional seam 允许无 provider）
        - 每个 DEFINITION 应该有至少一个 CONSUMER（使用者）
          （无 consumer 的 seam = 死代码，warn 但不报错）
        - PROVIDER 和 CONSUMER 必须引用已存在的 DEFINITION.seam_key
        """
        definitions: dict[str, PluginHandle] = {}
        providers: dict[str, list[PluginHandle]] = {}
        consumers: dict[str, list[PluginHandle]] = {}
        
        for h in handles:
            if h.manifest.kind == PluginKind.DEFINITION and h.manifest.seam_key:
                definitions[h.manifest.seam_key] = h
            elif h.manifest.kind == PluginKind.PROVIDER and h.manifest.seam_key:
                providers.setdefault(h.manifest.seam_key, []).append(h)
            elif h.manifest.kind == PluginKind.CONSUMER and h.manifest.seam_key:
                consumers.setdefault(h.manifest.seam_key, []).append(h)
        
        errors = []
        for key, defn in definitions.items():
            if key not in providers:
                errors.append(f"Seam '{key}' defined by {defn.entry_id} has no provider")
            if key not in consumers:
                _log.warning("seam_no_consumer", seam_key=key, definition=defn.entry_id)
        
        for key in providers:
            if key not in definitions:
                errors.append(f"Provider for unknown seam '{key}': {[h.entry_id for h in providers[key]]}")
        
        if errors:
            raise SeamCompletenessError(errors)
    
    async def _check_extension_points(self, handles: list[PluginHandle]) -> None:
        """
        校验 middleware 注册引用的扩展点是否已定义。
        PROVIDER/CONSUMER 的 middleware 字段必须引用已注册的 ExtensionPoint.seam_key。
        """
        defined_points = set()
        for h in handles:
            for ep in h.manifest.extension_points:
                defined_points.add(ep.seam_key)
        
        for h in handles:
            for mw_key in h.manifest.middleware:
                if mw_key not in defined_points:
                    raise ExtensionPointError(
                        f"Plugin {h.entry_id} registers middleware for "
                        f"undefined extension point '{mw_key}'"
                    )
```

#### 3.7.3 迁移路径

```
Phase A 期间：
  1. PluginManifest 新增 seam_key / extension_points / middleware 字段（§2.2.1）
  2. 每个现有 capability 包装为 DEFINITION/PROVIDER/CONSUMER plugin module
  3. register_seam_catalog() 的逻辑由 Loader._check_seam_completeness() 承担
  4. register_seam_catalog() 标记 @deprecated，内部改为调用 Loader 校验
  5. require_complete() 删除——Loader 已经做这件事

最终：
  无独立 seam 注册表。所有 seam 信息在 PluginManifest 中声明。
  Loader reconcile 自动校验完整性。
```

### 3.8 CognitiveRuntime 内部对 Plugin Middleware 开放

#### 3.8.1 问题

Spec §C.3 提到 Hook → AgentEvent Middleware 分离，但这只分离了"可阻断"和"不可阻断"两类。**CognitiveRuntime 内部的 perceive → think → act → reflect 循环仍然是硬编码调用**——loop 内核知道有哪些 hook，并在特定点调用它们。

这违反了 plugin-everything 自洽性：**loop 内核不应该知道 middleware 的存在，它只知道 phase 名称**。

#### 3.8.2 目标架构

```python
# lca/plugins/loop_cognitive/runtime.py
class CognitiveRuntime:
    """
    纯认知算法内核。不知道有哪些 middleware——只通过 MiddlewareRegistry 发射 phase 事件。
    
    横切关注点（日志、journal、budget check、content filter 等）全部由 plugin middleware 实现，
    注册到 MiddlewareRegistry，在 phase boundary 被自动调用。
    """
    def __init__(self, brain, body, memory, state_store, stop_rule,
                 middleware_registry: MiddlewareRegistry):
        self._brain = brain
        self._body = body
        self._memory = memory
        self._state_store = state_store
        self._stop_rule = stop_rule
        self._mw = middleware_registry  # 唯一的扩展接口
    
    async def step(self, state: AgentState) -> AgentState:
        ctx = self._make_phase_context(state)
        
        # perceive phase
        state = await self._mw.run("agent.before_perceive", "perceive", state, ctx)
        state = self._perceive(state)
        state = await self._mw.run("agent.after_perceive", "perceive", state, ctx)
        
        # think phase
        state = await self._mw.run("agent.before_think", "think", state, ctx)
        state = self._think(state)
        state = await self._mw.run("agent.after_think", "think", state, ctx)
        
        # act phase
        state = await self._mw.run("agent.before_act", "act", state, ctx)
        state = self._act(state)
        state = await self._mw.run("agent.after_act", "act", state, ctx)
        
        # reflect phase
        state = await self._mw.run("agent.before_reflect", "reflect", state, ctx)
        state = self._reflect(state)
        state = await self._mw.run("agent.after_reflect", "reflect", state, ctx)
        
        return state
    
    async def run_turn(self, state: AgentState) -> AgentState:
        """一个 turn = 多个 step 直到 stop_rule 触发"""
        while not self._stop_rule.should_stop(state):
            state = await self.step(state)
            # turn-end middleware（serial 模式，所有 middleware 都收到通知）
            await self._mw.run("agent.before_turn_end", "turn_end", state, ctx)
        return state
    
    # 以下方法是纯算法，不包含任何横切关注点
    def _perceive(self, state: AgentState) -> AgentState: ...
    def _think(self, state: AgentState) -> AgentState: ...
    def _act(self, state: AgentState) -> AgentState: ...
    def _reflect(self, state: AgentState) -> AgentState: ...
```

#### 3.8.3 原 Hook 系统的迁移映射

| 现有 Hook | 迁移目标 | 实现方式 |
|---|---|---|
| `journal_emitting_hook` | **删除**，由 `SessionStore.append()` 自动完成 | 不可阻断 → session core |
| `logging_hook` | `structlog` subscriber，监听 journal 事件 | 不可阻断 → observability plugin |
| `budget_check_hook` | `agent.before_step` middleware | 可阻断 → policy plugin |
| `loop_intervention_hook` | `agent.after_act` middleware | 可阻断 → policy plugin |
| `pre_think_hook` | `agent.before_think` middleware | 可阻断 → domain plugin |
| `pre_act_hook` | `agent.before_act` middleware | 可阻断 → domain plugin |
| `skill_activation_hook` | `agent.before_think` middleware | 可阻断 → skill plugin |

**关键**：CognitiveRuntime 自身不包含任何 journal 写入、日志记录、budget 检查、loop 干预代码。所有这些通过 middleware 注入。**loop 内核是纯算法，所有横切关注点都是 plugin。**

#### 3.8.4 Middleware Plugin 示例

```python
# lca/plugins/budget_policy/__init__.py
manifest = PluginManifest(
    id="lca.policy.budget",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.POLICY,
    seam_key="agent.pre_step",
    middleware=("agent.before_step",),  # 注册到 pre_step 扩展点
)

async def apply(ctx, config):
    registry = ScopedPluginHost.current().middleware
    registry.register(
        MiddlewareRegistration(seam_key="agent.before_step", priority=10, plugin_id="lca.policy.budget"),
        budget_check_middleware,
    )

async def budget_check_middleware(phase, state, context):
    if state.step_count >= config.get("max_steps", 100):
        raise BudgetExceededError(f"Step budget exhausted: {state.step_count}")
    return state  # 放行
```

#### 3.8.5 自洽性检验

改造完成后，以下横切关注点**全部由 plugin middleware 实现**，CognitiveRuntime 内核不包含任何硬编码关注点：

| 横切关注点 | Plugin | 扩展点 |
|---|---|---|
| Journal 事件写入 | `session_jsonl` (通过 SessionStore) | 不需要 middleware，append 时自动 |
| 日志 | `observability.console` (structlog subscriber) | 不需要 middleware |
| Budget 检查 | `budget_policy` | `agent.before_step` |
| Loop 干预（连续相同工具检测） | `loop_intervention_policy` | `agent.after_act` |
| Skill 激活 | `skill_activation` | `agent.before_think` |
| Content filter | `content_filter_policy` | `agent.request` |
| HIL approval | `hil_approval` | `tools.pre_execute` |

---

## 4. 迁移 Phase 详细规格

### Phase A：Plugin Tree 成为生产 Composition Root

**目标**：不改变任何认知语义，只让 production 使用 Profile + Loader。
**风险**：低——不触碰 Agent 行为。
**预计工作量**：1-2 周。

#### A.1 扩展 PluginSpec → PluginManifest 兼容

```python
# lca/harness/kernel/compat.py
class LegacyPluginAdapter:
    """让现有 PluginSpec module 自动被新 Loader 接受"""
    @staticmethod
    def to_manifest(module_or_spec, entry_id: str) -> PluginManifest:
        if isinstance(module_or_spec, PluginSpec):
            spec = module_or_spec
        else:
            spec = Loader._build_spec(PluginEntry(id=entry_id, module=module_or_spec))
        return PluginManifest(
            id=entry_id,
            version="0.0.0-legacy",
            api_version="lca-harness/0",
            kind=PluginKind.PROVIDER,
            provides=(spec.provides,) if spec.provides else (),
            requires=spec.inject,
        )
```

**验收测试**：
- 现有 `tests/plugin/` 全部通过
- 新 Loader 能加载旧 module shape

#### A.2 拆分 boot_capabilities() 为 plugin modules + base-spine bundle

将 `capability_boot.py` 中的每个 `mount` 拆为独立 plugin module：

```yaml
# bundles/base-spine.yaml
apiVersion: lca.ai/harness/v1
bundle: base-spine
entries:
  - id: lca.llm.service
    module: lca.plugins.llm_service
    config: {}
  - id: lca.memory.service
    module: lca.plugins.memory_service
    config: {}
  - id: lca.state_store.service
    module: lca.plugins.state_store_service
    config: {}
  - id: lca.tools.service
    module: lca.plugins.tools_service
    config: {}
  - id: lca.transport.service
    module: lca.plugins.transport_service
    config: {}
  - id: lca.skills.service
    module: lca.plugins.skills_service
    config: {}
  - id: lca.observability.service
    module: lca.plugins.observability_service
    config: {}
```

每个 plugin module 形如：

```python
# lca/plugins/llm_service/__init__.py
from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca.llm.service",
    provides=("llm",),
    layer="L0",
    effects="none",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.capability.llm import LlmService
    service = LlmService()
    # 注册 default providers
    from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
    service.register("mock", MockLLMAdapter())
    ctx.provide("llm", service)
```

**验收测试**：
- `Loader.load(base_spine_entries)` 产生的 service table 等价于 `boot_capabilities()`
- `ctx.require("llm")` 等 SeamKey 解析结果不变

#### A.3 生产 Profile 文件

```yaml
# profiles/web-standard.yaml
apiVersion: lca.ai/harness/v1
profile: web-standard
bundles:
  - bundles/base-spine.yaml
  - bundles/python-cognitive.yaml
  - bundles/web-gateway.yaml
  - bundles/observability.yaml
patch:
  - id: lca.llm.provider
    config:
      provider: deepseek
      model: deepseek-chat
  - id: lca.loop.provider
    config:
      provider: lca.loop.cognitive
  - id: lca.session.persistence
    config:
      backend: jsonl
      path: .lca/sessions/
```

#### A.4 Gateway startup 加载 profile

```python
# gateway/app.py 改造
async def create_app():
    profile = ProfileLoader.load("profiles/web-standard.yaml")
    tree = await Loader().load(profile.entries)
    host = tree.host

    # 将 resolved host 注入到 Gateway 依赖
    app = build_starlette_app(host)
    app.state.plugin_host = host
    app.state.profile_digest = profile.digest()
    return app
```

#### A.5 AgentComposer 接收 resolved scope

```python
class AgentComposer:
    def compose(self, spec: AgentSpec, *, scope: ScopedPluginHost = None, **kw):
        if scope is not None:
            # 从 scope 解析能力
            llm_rt = scope.resolve("llm")
            mem_svc = scope.resolve("memory")
            # ... 其余不变
        else:
            # 兼容旧路径：boot_capabilities()
            ctx = boot_capabilities()
            # ... 旧逻辑
```

#### A.6 `lca inspect tree` 命令

```python
# scripts/lca_ops.py 扩展
def cmd_inspect_tree(profile_path: str):
    profile = ProfileLoader.load(profile_path)
    tree = Loader().load_sync(profile.entries)
    for handle in tree.host.handles.values():
        print(f"  {handle.entry_id}")
        print(f"    state: {handle.state}")
        print(f"    provides: {handle.spec.provides}")
        print(f"    inject: {handle.injected}")
        print(f"    effects: {len(handle.effects)}")
    print(f"  tree digest: {profile.digest()}")
```

#### A.7 Seam Catalog 迁移为 Loader reconcile pass

```python
# 1. 每个现有 capability 包装为 DEFINITION/PROVIDER/CONSUMER plugin module

# lca/plugins/seam_definitions/__init__.py
"""原 register_seam_catalog() 的声明式替代"""
manifest = PluginManifest(
    id="lca.seam.definitions",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.BUNDLE,  # 纯声明，无逻辑
    extension_points=(
        ExtensionPoint(seam_key="llm", dispatch_mode="waterfall", description="LLM adapter"),
        ExtensionPoint(seam_key="sandbox", dispatch_mode="waterfall", description="Sandbox runtime"),
        ExtensionPoint(seam_key="memory", dispatch_mode="waterfall", description="Memory system"),
        ExtensionPoint(seam_key="state_store", dispatch_mode="waterfall", description="State store"),
        ExtensionPoint(seam_key="search", dispatch_mode="waterfall", description="Search provider"),
        ExtensionPoint(seam_key="tools", dispatch_mode="waterfall", description="Tool executor"),
        ExtensionPoint(seam_key="transport", dispatch_mode="waterfall", description="Agent transport"),
        ExtensionPoint(seam_key="skills", dispatch_mode="waterfall", description="Skill store"),
        ExtensionPoint(seam_key="file_store", dispatch_mode="waterfall", description="File store"),
        ExtensionPoint(seam_key="observability", dispatch_mode="waterfall", description="Observability backend"),
    ),
)

# 2. register_seam_catalog() 标记 @deprecated，内部改为调用 Loader 校验
def register_seam_catalog() -> None:
    """@deprecated: Loader._check_seam_completeness() 已替代此函数。
    过渡期保留，内部实现改为从已加载的 PluginManifest 收集 seam 信息并校验。"""
    import warnings
    warnings.warn("register_seam_catalog() is deprecated; Loader handles seam completeness", DeprecationWarning)
    # 从已加载 plugin tree 中收集 seam 信息并校验
    current_host = ScopedPluginHost.current()
    seam_defs = {}
    seam_providers = {}
    seam_consumers = {}
    for handle in current_host._handles.values():
        m = handle.manifest
        if m.seam_key:
            if m.kind == PluginKind.DEFINITION:
                seam_defs[m.seam_key] = m.id
            elif m.kind == PluginKind.PROVIDER:
                seam_providers.setdefault(m.seam_key, []).append(m.id)
            elif m.kind == PluginKind.CONSUMER:
                seam_consumers.setdefault(m.seam_key, []).append(m.id)
    # 复用 Loader 的校验逻辑
    _validate_seam_completeness(seam_defs, seam_providers, seam_consumers)

# 3. require_complete() 删除
# Loader reconcile 已经校验完整性，require_complete() 不再有存在必要
```

**Phase A 验收**：
1. 同一 AgentSpec + mock LLM + calculator 工具的结果/Journal/trace 与现有基线等价
2. `AgentComposer.compose(spec, scope=profile_scope)` 不直接 import/mount default provider
3. `lca inspect tree --profile profiles/web-standard.yaml` 输出完整 plugin tree
4. 旧路径 `AgentComposer.compose(spec)` 仍然工作（兼容）
5. `register_seam_catalog()` 标记 `@deprecated`，无新调用方
6. Loader reconcile 通过 seam completeness check（等价于原 `require_complete()`）

---

### Phase B：Session/Agent Spine + Gateway Command 化

**目标**：前端和后端通过 Agent Session 而不是 `RunSession.runnable` 相连。
**风险**：中——触碰 Gateway 执行路径，需要双写对账。
**预计工作量**：2-3 周。

#### B.1 SessionStore 扩展 RunStore

在现有 `RunStore` 基础上扩展，不重写：

```python
# lca/harness/session/store.py
class SessionStore:
    """
    包装现有 RunStore，增加：
    - SessionHeader
    - 新事件词表（turn/step/context/tool/skill/subagent）
    - 多 projector 统一驱动
    """
    def __init__(self, run_store: RunStore, header: SessionHeader):
        self._store = run_store
        self._header = header

    async def append(self, event_data, **kwargs) -> SessionEvent:
        # 转换为 RunStore 可接受的格式
        journal_event = _to_journal_event(event_data, self._header, **kwargs)
        self._store.append(journal_event)
        return journal_event
```

#### B.2 AgentRegistry

新增模块，不修改现有 RunRegistry：

```python
# lca/harness/agent/registry.py
# 见 3.3 节
```

#### B.3 Gateway 双写模式

```python
# gateway/runs/execute.py 改造（shadow 模式）
async def execute_run(registry, *, run_id, question, mode):
    session = registry.get(run_id)

    # 旧路径
    if not MIGRATION_FLAGS["session_spine"]:
        return await _legacy_execute(session, ...)

    # 新路径：创建 SessionStore + AgentRegistry entry
    session_store = await _create_session_store(session)
    agent_handle = await agent_registry.create(
        profile=session.profile or "web-standard",
        session_id=session.run_id,
    )

    # shadow 模式：两条路径同时运行，对比结果
    if MIGRATION_FLAGS["session_spine"] == "shadow":
        legacy_result = await _legacy_execute(session, ...)
        new_result = await agent_handle.agent.followup(...)
        _compare_results(legacy_result, new_result)
        return legacy_result

    # authoritative 模式
    receipt = await agent_handle.agent.followup(UserMessage(content=question))
    # 结果从 projection 获取
    ...
```

#### B.4 新 API endpoints

```python
# lca/plugins/gateway_starlette/routes.py
routes = [
    # 新 API
    Route("POST /v1/sessions", handle_create_session),
    Route("POST /v1/sessions/{id}/messages", handle_send_message),
    Route("GET  /v1/sessions/{id}/snapshot", handle_snapshot),
    Route("GET  /v1/sessions/{id}/events", handle_sse_events),
    Route("POST /v1/sessions/{id}/commands/answer", handle_answer),
    Route("POST /v1/sessions/{id}/commands/cancel", handle_cancel),
    Route("POST /v1/sessions/{id}/commands/steer", handle_steer),

    # 旧 API 保留为 compatibility adapter
    Route("POST /runs", handle_legacy_create),      # 内部转译为 create + followup
    Route("GET  /runs/{id}", handle_legacy_status),  # 内部转译为 snapshot
    Route("GET  /runs/{id}/live", handle_legacy_sse),
    Route("POST /runs/{id}/answer", handle_legacy_answer),
]
```

#### B.5 HIL resume 不再依赖内存 runnable

```python
# 旧：
async def resume_run(session, registry, answer):
    result = await session.runnable.resume(session.snapshot, input=answer)

# 新：
async def handle_answer(cmd: AnswerCommand):
    # 1. append approval.resolved event
    await session_store.append(ToolApprovalResolved(
        call_id=cmd.answer,
        decision="approved",
    ))
    # 2. agent registry resume 或 wake
    agent = agent_registry.get(cmd.session_id)
    if agent is None:
        # 进程重启恢复
        agent_handle = await agent_registry.resume(cmd.session_id)
        agent = agent_handle.agent
    await agent.followup(UserMessage(content=cmd.answer))
```

#### B.6 双写对账协议

**问题**：shadow 模式下 `_compare_results(legacy_result, new_result)` 中 `legacy_result` 是 `TaskResult`，`new_result` 是 `ProjectionSnapshot`——结构完全不同。

**解决方案**：定义 `ResultNormalizer`，将两种结果归一化为可比对的中间格式。

```python
# lca/harness/diagnostics/normalizer.py
@dataclass(frozen=True)
class NormalizedResult:
    """双写对账的中间格式——两条路径都必须产出此格式"""
    status: str                    # "completed" | "failed" | "input_required" | "canceled"
    answer: str | None             # 最终文本回复
    tool_calls: tuple[NormalizedToolCall, ...]   # 有序工具调用序列
    llm_calls: int                 # LLM 调用次数
    error: str | None = None
    journal_event_types: tuple[str, ...]         # 有序事件类型列表

@dataclass(frozen=True)
class NormalizedToolCall:
    tool_name: str
    arguments_hash: str            # 参数 hash，不存完整参数
    success: bool
    result_hash: str | None

class ResultNormalizer:
    """将 TaskResult 和 ProjectionSnapshot 归一化"""
    
    @staticmethod
    def from_task_result(result: TaskResult) -> NormalizedResult:
        return NormalizedResult(
            status=result.status.value,
            answer=result.answer,
            tool_calls=tuple(
                NormalizedToolCall(tc.name, _hash(tc.arguments), tc.success, _hash(tc.result))
                for tc in result.tool_calls
            ),
            llm_calls=result.llm_calls,
            error=result.error,
            journal_event_types=tuple(e.type for e in result.journal_events),
        )
    
    @staticmethod
    def from_projection(snapshot: ProjectionSnapshot, journal: list[SessionEvent]) -> NormalizedResult:
        conversation = snapshot.values.get("conversation")
        activity = snapshot.values.get("activity")
        return NormalizedResult(
            status=activity.get("status", "unknown"),
            answer=conversation.get("last_assistant_message"),
            tool_calls=tuple(
                NormalizedToolCall(tc["name"], tc["args_hash"], tc["success"], tc.get("result_hash"))
                for tc in _extract_tool_calls(journal)
            ),
            llm_calls=sum(1 for e in journal if e.type == "model.completed.v1"),
            journal_event_types=tuple(e.type for e in journal),
        )

async def _compare_results(legacy: TaskResult, new_snapshot: ProjectionSnapshot,
                           new_journal: list[SessionEvent]) -> DivergenceReport:
    norm_legacy = ResultNormalizer.from_task_result(legacy)
    norm_new = ResultNormalizer.from_projection(new_snapshot, new_journal)
    
    divergences = []
    if norm_legacy.status != norm_new.status:
        divergences.append(f"status: {norm_legacy.status} != {norm_new.status}")
    if norm_legacy.tool_calls != norm_new.tool_calls:
        divergences.append(f"tool_calls: {len(norm_legacy.tool_calls)} vs {len(norm_new.tool_calls)}")
    if norm_legacy.llm_calls != norm_new.llm_calls:
        divergences.append(f"llm_calls: {norm_legacy.llm_calls} vs {norm_new.llm_calls}")
    
    report = DivergenceReport(
        run_id=...,
        divergences=divergences,
        legacy=norm_legacy,
        new=norm_new,
    )
    if divergences:
        _log.warning("shadow_divergence", report=report.to_dict())
    return report
```

#### B.7 旧 API → 新 API 翻译层（同步/异步桥接）

**核心难题**：旧 `/runs` 是**同步返回结果**（`await runnable.run(question)` → `TaskResult`），新 `/v1/sessions` 是**异步的**（`POST /sessions` → 返回 session_id → polling `GET /snapshot`）。

```python
# lca/plugins/gateway_starlette/legacy_adapter.py
class LegacyApiAdapter:
    """
    将旧 /runs/* API 的请求翻译为新 command，并将异步结果桥接为同步返回。
    
    关键设计：
    - POST /runs → 内部执行 SessionCreate + MessageSend + wait_for_completion
    - GET /runs/{id} → 内部执行 ProjectionSnapshot → TaskResult 格式
    - GET /runs/{id}/live → 内部订阅 ProjectionChange → SSE 格式适配
    - POST /runs/{id}/answer → 内部执行 AnswerCommand
    
    wait_for_completion 的超时策略：
    - 默认等待 120s
    - 如果 agent 进入 waiting_input 状态，立即返回（等价于 INPUT_REQUIRED）
    - 如果超时，返回当前 projection snapshot（等价于 RUNNING）
    """
    
    async def handle_legacy_create(self, request) -> Response:
        """POST /runs → create session + send message + wait for result"""
        body = await request.json()
        
        # 1. Create session
        create_receipt = await self._gateway.handle_create_session(SessionCreateCommand(
            idempotency_key=new_id("idem"),
            profile=body.get("profile", "web-standard"),
        ))
        session_id = create_receipt.session_id
        
        # 2. Send message
        send_receipt = await self._gateway.handle_send_message(MessageSendCommand(
            idempotency_key=new_id("idem"),
            session_id=session_id,
            content=body["question"],
        ))
        
        # 3. Wait for completion (桥接异步为同步)
        result = await self._wait_for_terminal_state(session_id, timeout_s=120)
        
        # 4. 翻译为旧 TaskResult 格式
        return JSONResponse(_projection_to_task_result(result, session_id))
    
    async def handle_legacy_status(self, request) -> Response:
        """GET /runs/{id} → projection snapshot → TaskResult 格式"""
        session_id = self._run_id_to_session_id(request.path_params["id"])
        snapshot = await self._gateway.get_snapshot(session_id)
        return JSONResponse(_projection_to_task_result(snapshot, session_id))
    
    async def handle_legacy_sse(self, request) -> StreamingResponse:
        """GET /runs/{id}/live → ProjectionChange SSE → LiveTail SSE 格式"""
        session_id = self._run_id_to_session_id(request.path_params["id"])
        
        async def event_stream():
            async for change in self._gateway.subscribe_changes(session_id, last_seq=0):
                # 将 ProjectionChange 翻译为旧 LiveTail SSE 格式
                yield _projection_change_to_live_tail_event(change)
        
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    
    async def _wait_for_terminal_state(self, session_id: str, timeout_s: int) -> ProjectionSnapshot:
        """等待 session 到达终态或超时"""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            snapshot = await self._gateway.get_snapshot(session_id)
            status = snapshot.values.get("activity", {}).get("status")
            if status in {"completed", "failed", "canceled", "waiting_input"}:
                return snapshot
            await asyncio.sleep(0.2)
        return await self._gateway.get_snapshot(session_id)  # 超时返回当前状态
```

#### B.8 SSE 水位线对齐

**问题**：双写模式下有两条 SSE 流——旧 `LiveTail` 和新 `ProjectionChange`。它们的水位线定义不同：
- 旧 LiveTail：基于 journal event index
- 新 ProjectionChange：基于 `ProjectionChange.seq`（projection 的水位线）

```python
class SSEAligner:
    """
    确保旧 SSE 和新 SSE 在相同 journal seq 时推送等价信息。
    
    策略：
    - 新 SSE 的 Last-Event-ID = journal seq
    - 旧 SSE 的 Last-Event-ID = journal event index（与 seq 等价）
    - 翻译层确保两者基于相同 journal seq 推送
    - reconnect 时，从 Last-Event-ID 开始补发缺失的 ProjectionChange
    """
    
    async def subscribe_with_reconnect(self, session_id: str, last_seq: int) -> AsyncIterator[ProjectionChange]:
        """带 reconnect 的 SSE 订阅"""
        # 1. 获取当前 seq
        current_seq = await self._session_store.current_seq(session_id)
        
        # 2. 补发 last_seq → current_seq 之间的 changes
        if last_seq < current_seq:
            async for change in self._replay_from_journal(session_id, last_seq + 1, current_seq):
                yield change
        
        # 3. 订阅实时 changes
        async for change in self._projection_registry.subscribe_changes(session_id, current_seq):
            yield change
```

#### B.9 回退策略与不可回退点

```python
# MIGRATION_FLAGS 生命周期
MIGRATION_FLAGS = {
    "session_spine": "off",       # → "shadow" → "authoritative" → "legacy_removed"
}

# 阶段转换条件：
# off → shadow:
#   条件: A.1-A.7 验收通过
#   回退: 设回 "off" 即可，无数据影响
#
# shadow → authoritative:
#   条件: shadow 模式连续 7 天零 divergence
#   回退: 设回 "shadow"，新路径产生的 session 需要手动映射到旧 session
#   ⚠️ 不可回退点: 如果有 session 已经在新路径上创建了，回退到 shadow 后旧路径
#      会重新执行这些 session（重复执行风险）
#
# authoritative → legacy_removed:
#   条件: 所有前端切换到 /v1/sessions API
#   回退: 需要重新部署 LegacyApiAdapter
#   ⚠️ 不可回退点: 旧 /runs/* route handler 被删除后无法恢复
#
# 保护机制：
# - authoritative 阶段旧 /runs/* 保留，通过 LegacyApiAdapter 翻译
# - 只有在 legacy_removed 阶段才删除旧 route handler
# - 删除前必须有 30 天观察期，确认无流量
```

**Phase B 验收**：
1. 网关重启后可以从 JSONL 恢复 waiting-input session
2. SSE 从 Last-Event-ID 补齐
3. 前端 snapshot 同一 watermark 下 status/activity 一致
4. 旧 `/runs/*` API 行为不变（通过 LegacyApiAdapter 翻译）
5. shadow 模式下 `ResultNormalizer` 对账零 divergence（连续 100 次测试 run）
6. 双写模式下两条 SSE 流在相同 journal seq 推送等价信息
7. 回退到 "off" 后系统完全恢复正常行为

---

### Phase C：CognitiveRuntime 成为可替换 Loop Provider

**目标**：完全保留 LCA 认知优势，消除 loop 特权。
**风险**：中——重构 Runtime 的依赖获取方式。
**预计工作量**：2-3 周。

#### C.1 AgentLoopFactory + LiveAgent 接口

见 2.2.4 节。

#### C.2 CognitiveLoopFactory 薄适配

```python
# lca/plugins/loop_cognitive/factory.py
# 见 3.5 节
```

#### C.3 Hook → Phase Middleware 全面开放

**目标**：CognitiveRuntime 内部不再硬编码任何横切关注点。所有可阻断逻辑通过 MiddlewareRegistry 注入。详见 §3.8。

**改造步骤**：

1. **CognitiveRuntime 构造函数接受 MiddlewareRegistry**：
   ```python
   class CognitiveRuntime:
       def __init__(self, brain, body, memory, state_store, stop_rule,
                    middleware_registry: MiddlewareRegistry):  # 新增
   ```

2. **每个 phase boundary 插入 middleware 调用**：
   ```python
   # 在 perceive/think/act/reflect 前后调用 middleware_registry.run()
   # 见 §3.8.2 完整实现
   ```

3. **现有 Hook 逐个迁移为 Plugin Middleware**：

   | 现有 Hook | 迁移目标 Plugin | 注册扩展点 | 优先级 |
   |---|---|---|---|
   | `budget_check_hook` | `lca.policy.budget` | `agent.before_step` | 10 |
   | `loop_intervention_hook` | `lca.policy.loop_intervention` | `agent.after_act` | 20 |
   | `pre_think_hook` | `lca.cognitive.pre_think` | `agent.before_think` | 50 |
   | `pre_act_hook` | `lca.cognitive.pre_act` | `agent.before_act` | 50 |
   | `skill_activation_hook` | `lca.skill.activation` | `agent.before_think` | 60 |
   | `journal_emitting_hook` | **删除** → SessionStore 自动做 | — | — |
   | `logging_hook` | **删除** → structlog subscriber | — | — |

4. **验收条件**：
   - CognitiveRuntime 源码中不出现 `hook`、`log`、`journal.append` 等硬编码调用
   - 所有横切关注点通过 plugin middleware 注入
   - 替换 loop provider（如 ReplayLoop）不需要迁移任何 hook 逻辑

#### C.4 AgentState 由 projector materialize

```python
class AgentStateProjection:
    """从 Journal events 重建 AgentState"""
    key = "agent_state"
    version = 1

    def init(self):
        return AgentState(...)

    def apply(self, state, event):
        if event.type == "turn.started":
            state.step = 0
        elif event.type == "step.ended":
            state.step = event.data["step"] + 1
        elif event.type == "tool.completed":
            # 重建 history
            ...
        return state

    def view(self, state):
        return state
```

#### C.5 Replay Loop

```python
# lca/plugins/loop_replay/factory.py
class ReplayLoopFactory:
    """Deterministic replay from golden journal"""
    async def create(self, scope, identity, options, *, resume_session=None):
        journal = scope.resolve("sessions")
        return ReplayLiveAgent(journal, identity)

class ReplayLiveAgent:
    """重放 journal 中的事件，不真正调用 LLM"""
    async def followup(self, message):
        # 从 journal 重建下一步
        ...
```

**Phase C 验收**：
1. 新插件可只依赖 `agents/sessions/tools` 扩展行为，不 import `CognitiveRuntime`
2. 替换为 test loop/replay loop 不改 Gateway
3. golden journal 复跑结果确定

---

### Phase D：DSH Bridge Provider 化

**目标**：DSH 是 loop/subagent provider，不是网关特殊分支。
**风险**：中——需要映射 DSH 事件到 LCA 事件词表。
**预计工作量**：1-2 周。

#### D.1 消除 Gateway if/else

```python
# 旧：
if is_dsh_driver(session.execution_target):
    await execute_dsh_session(session)
else:
    runnable = build_solo_agent(...)

# 新：profile/preset 决定 loop provider
# profiles/dsh-bridge.yaml
# patch:
#   - id: agent-loop
#     config:
#       provider: lca.loop.dsh_bridge
```

#### D.2 DSH → SessionEvent 映射

```python
# lca/plugins/loop_dsh_bridge/event_mapping.py
DSH_EVENT_MAP = {
    "agent/created": "session.created.v1",
    "turn/start": "turn.started.v1",
    "turn/end": "turn.ended.v1",
    "step/start": "step.started.v1",
    "step/end": "step.ended.v1",
    "user/message": "message.accepted.v1",
    "assistant/message": "model.completed.v1",
    "tool/call": "tool.called.v1",
    "tool/result": "tool.completed.v1",
}

class DshJournalProjector:
    """将 DSH notification 转换为 LCA SessionEvent"""
    def project(self, dsh_event):
        lca_type = DSH_EVENT_MAP.get(dsh_event.type)
        if lca_type is None:
            return  # unknown → skip with warning
        return SessionEvent(type=lca_type, ...)
```

**Phase D 验收**：
1. 同一 UI 和 SSE 不因 loop 选择而改变
2. parent/child session tree 可以混用 Cognitive 与 DSH provider

---

### Phase E：Tool Pipeline、Skills、Subagents 收敛

**目标**：所有扩展能力进入同一 Session/Scope/Policy 模型。
**风险**：高——面积大。
**预计工作量**：3-4 周。

见蓝图 Section 8-10，此处不重复。关键是：
1. Tool Definition/Provider/Pipeline/Renderer 分离
2. Skill Catalog/Tool/Slash/Projection 统一
3. SubagentRegistry + capability negotiation + SubagentActivationCoordinator
4. Workflow DAG engine

---

## 5. 测试策略

### 5.1 测试金字塔

| 层级 | 测试内容 | 对应文件 |
|---|---|---|
| **Plugin lifecycle** | 依赖、effect LIFO、cascade unload、scope release、config rollback | `tests/harness/test_kernel_*.py` |
| **Profile composition** | bundle order、patch provenance、manifest version、tree digest | `tests/harness/test_profile_*.py` |
| **Session invariant** | seq 连续、event immutable、append-before-observe、FIFO inbox | `tests/harness/test_session_*.py` |
| **Projection determinism** | full fold = checkpoint + tail replay | `tests/harness/test_projection_*.py` |
| **Loop compatibility** | CognitiveLoopFactory 与旧 CognitiveRuntime 在 mock fixture 上等价 | `tests/harness/test_loop_cognitive_*.py` |
| **Gateway protocol** | create/followup/steer/inject/cancel/answer、SSE reconnect、idempotency | `tests/harness/test_command_gateway_*.py` |
| **Tool/security** | denial/approval/retry/sandbox/redaction | `tests/harness/test_tool_pipeline_*.py` |
| **Subagent/workflow** | lineage、depth、tool filter、child cancellation、parent drain | `tests/harness/test_subagent_*.py` |
| **Architecture** | gateway 不 import concrete loop；contracts 不 import implementation | `tests/test_layer_boundary.py` `tests/test_architecture_*.py` |

### 5.2 迁移安全：双写对账

```python
# tests/harness/test_migration_divergence.py
async def test_shadow_mode_no_divergence():
    """shadow 模式下旧路径和新路径必须产生等价结果"""
    legacy_result = await legacy_execute(spec, mock_llm, tools)
    new_result = await new_execute(spec, mock_llm, tools)

    # 终态等价
    assert legacy_result.status == new_result.status
    # 工具调用序列等价
    assert legacy_result.tool_calls == new_result.tool_calls
    # Journal 事件等价（忽略 plugin_id/version 等 meta 差异）
    assert normalize(legacy_journal) == normalize(new_journal)
```

---

## 6. 决策记录

### 6.1 为什么不重写 Plugin Kernel

现有 `PluginHost/Context/Lifecycle/Loader` 已经是生产质量的 Python Cordis：
- Host 纯数据容器，职责清晰
- Context 是 plugin 唯一 API，mount/effect/waterfall/child 齐全
- Lifecycle 有 LIFO disposal、cascade deactivation、config rollback
- Loader 有 validation、cycle detection、reconcile

重写不会增加任何结构性收益，只会引入回归风险。

### 6.2 为什么不删除 CognitiveRuntime

它是 LCA 最有价值的认知资产：
- perceive → think → act → reflect 闭环
- HIL resume via checkpoint
- Loop intervention（连续工具检测）
- Budget management
- Skill activation scope

删除它 = 删除 LCA 的产品差异化。正确做法是包装为第一个 provider。

### 6.3 为什么不在第一步物理重组目录

`layer0` → `layer3` 的物理目录承载了团队心智模型和 import lint 规则。第一步只在逻辑层建立新 spine（`lca/harness/`、`lca/plugins/`），通过 re-export 和 adapter 连接旧目录。等 spine 稳定后再渐进收敛物理结构。

### 6.4 为什么 Python 不依赖 DSH 的 Cordis ABI

- Cordis 是 TypeScript-only，依赖 declaration merging、template literal types、conditional types 等 Python 无法直接复制的类型系统特性
- LCA 是 Python 项目，应该有自己稳定的 Python SPI
- DSH 是设计标杆和可选的外部 provider，不是编译依赖

### 6.5 为什么 SessionStore 包装 RunStore 而不是重写

`RunStore` 已经有 append-only、seq、frozen event、scope stamping、redaction、projectors、JSONL/SSE/OTel/Langfuse reader。这是最难后来补上的资产。重写会丢失所有已验证的不变量。

### 6.6 Agent 与 Session 的 1:1 关系：当前选择

**决策**：在 Phase B/C/D 期间，Agent 与 Session 保持 **1:1** 关系。`AgentRegistry` 以 `session_id` 为 key，每个 session 恰好一个 live agent。

**理由**：
- DSH 也是 1:1（AgentHandle 持有唯一 Agent，绑定唯一 Session）
- 1:N（一个 Agent 跨多个 Session）的场景在 LCA 当前产品中不存在
- 过早引入 N:M 会增加概念负担和实现复杂度

**未来扩展路径**：
- 如果需要"Agent 模板"概念（跨 session 复用），引入 `AgentTemplate = Profile + Preset + Options`
- `AgentTemplate` 是配置，不是运行实体
- `AgentInstance = Session + Handle` 仍然是 1:1
- 届时 `AgentRegistry` 可以拆为 `TemplateRegistry` + `SessionRegistry`

**不变量**：只要 1:1 成立，`AgentRegistry` 等价于 `SessionRegistry`，不需要为 "Agent 在哪里" 这个问题维护额外的查找表。

### 6.7 物理目录 deprecation 时间线

**决策**：不在第一步物理重组目录，但明确 deprecation 时间线，避免"以后再说"变成"永远不说"。

| Phase | `layer0`~`layer4` 状态 | `lca/harness/` 状态 | 动作 |
|---|---|---|---|
| Phase A 完成 | 保留，import lint 仍生效 | 新建，通过 re-export 连接 | `infrastructure/plugin/kernel` 标记为 `lca/harness/kernel` 的实现源 |
| Phase B 完成 | 保留 | 稳定 | 旧 `RunStore`、`RunRegistry` 标记 `@deprecated` |
| Phase C 完成 | `runtime/runtime_loop.py` 标记 `@deprecated` | `loop_cognitive` 成为唯一入口 | `CognitiveRuntime` 移入 `lca/plugins/loop_cognitive/` 内部 |
| Phase D 完成 | `gateway/runs/dsh_execute.py` 删除 | `loop_dsh_bridge` 成为唯一入口 | Gateway 不再有 DSH 分支 |
| Phase E 完成 | `cognition` 保留（Brain/Body/Memory 算法） | `lca/plugins/` 承载所有运行时扩展 | `capability_boot.py` 删除 |
| **收敛期**（Phase E 后 1-2 月） | 逐步将 re-export 转为物理移动 | 物理目录成为主要结构 | import lint 规则更新 |
| **终态** | `layer0`~`layer4` 只保留算法代码（Brain/Body/Memory/Team/roles） | `lca/harness/` + `lca/plugins/` 承载所有运行时 | `layer` 目录不再包含运行时/装配逻辑 |

**强制约束**：每个 Phase 完成时，必须更新此表，记录哪些旧路径被标记 `@deprecated`、哪些被删除。

### 6.8 SessionStore.append() 并发安全

**决策**：`SessionStore.append()` 使用 `_seq_lock: asyncio.Lock` 保证 seq 分配的原子性。

**理由**：
- 两个 command 可能同时到达（如 user message + tool approval answer）
- seq 必须单调递增且无间隙，需要原子 read-then-increment
- Python asyncio 是单线程协作式，但在 `await` 点可能被切换
- 不使用数据库级 CAS 或乐观锁——单进程内 asyncio.Lock 足够

```python
class SessionStore:
    def __init__(self, ...):
        self._seq = -1
        self._seq_lock = asyncio.Lock()
    
    async def append(self, event_data, **kwargs) -> SessionEvent:
        async with self._seq_lock:
            self._seq += 1
            seq = self._seq
        # seq 已分配，后续操作可并发
        event = SessionEvent(seq=seq, ...)
        await self._persistence.write(event)
        await self._notify_projectors(event)  # projector 可以并发 fold
        return event
```

**ProjectionRegistry 并发**：
- 多个 projector 可以并发 fold 同一个 event（只读）
- 但 projector 的 checkpoint 写入必须串行（通过 `_checkpoint_lock`）
- 如果某个 projector 落后超过 N 个 event，触发 backpressure warning

### 6.9 Plugin 热替换安全域定义

**决策**：`reload` 字段的三种模式有明确定义：

| reload 模式 | 含义 | 安全条件 |
|---|---|---|
| `never` | 替换需要重启进程 | 无安全条件 |
| `restart_scope` | 替换需要 drain 并重建当前 scope | scope 内无 live agent |
| `hot_safe` | 替换不影响正在运行的 agent/session | 见下 |

**`hot_safe` 的严格定义**：一个 plugin 是 hot-safe 的，当且仅当：
1. 它不持有 per-session 可变状态（所有状态在 SessionStore/journal 中）
2. 它的 config 变更不影响已创建的 agent 的行为（只影响新创建的）
3. 它的 service 接口向后兼容（新版本实现旧 Protocol）
4. 它不在 middleware 调用链的关键路径上（或者 middleware 注册/注销是 atomic 的）

**违反任何条件 → 该 plugin 不能标记 `hot_safe`**。

---

## 7. 最终验收标准

| 问题 | 达标标准 |
|---|---|
| 换模型/sandbox/memory/loop 是否需要改 Gateway/Composer 源码？ | 否；Profile/Preset binding 改动即可 |
| 前端发一个消息是否直接调用某个 Python Agent 类？ | 不会；前端只提交 command |
| 前端状态是否由 raw token/event 猜测？ | 不会；由 server-side projection 提供 |
| 模型上下文是否能完全重建？ | 能；每一段都有 durable event/source reference |
| 现有认知闭环和 Team 优势是否仍在？ | 在；它们分别是 default loop 和 team provider |
| DSH 是否仍需 Gateway 特例？ | 不需；它是 loop/subagent provider |
| Skill 是否能被模型发现 + 用户显式调用 + 重放？ | 能；catalog/activation/result 都是 Session facts |
| 子代理是否可恢复、可取消、可追溯？ | 能；durable child session + SubagentActivationCoordinator |
| Plugin 是否可安全卸载/回滚？ | 能；scope-bound effects + drain |
| 运维是否能解释一次行为由哪个版本的插件造成？ | 能；event 中有 profile digest + plugin/version |

### Plugin-Everything 自洽性验收

| 问题 | 达标标准 |
|---|---|
| 系统是否有不走 plugin 路径的硬编码？ | 无；所有 capability 通过 PluginManifest 声明 |
| 扩展行为是否有唯一方式？ | 是；写一个 plugin（DEFINITION/PROVIDER/CONSUMER/POLICY） |
| Seam 完整性是否自动校验？ | 是；Loader reconcile 的 `_check_seam_completeness()` pass |
| CognitiveRuntime 内部是否对 plugin 开放？ | 是；每个 phase boundary 通过 MiddlewareRegistry 调用 plugin middleware |
| Gateway 是否 import 任何 concrete 实现？ | 否；只 import contracts/harness/{command, projection, session} |
| Plugin 代码能否透明获取当前 scope？ | 能；`ScopedPluginHost.current()` 通过 ContextVar 自动传递 |
| 替换一个 provider 是否需要改代码？ | 否；改 profile YAML 的 patch 段 |
| 横切关注点（budget/logging/intervention）是否由 plugin 实现？ | 是；见 §3.8.3 迁移映射表 |

---

## 8. 补充分析：Spec 必须覆盖的横切关注点

### 8.1 性能模型

#### ProjectionRegistry 吞吐

```
N projections × M events/turn = O(N×M) fold per turn

典型值：
- N = 5-10 projections（conversation, activity, status, skills, agent_state, tools）
- M = 20-50 events/turn（step + perceive + think + act + reflect + tool + llm）
- 单次 fold 耗时 < 0.1ms（纯函数，dict update）
- 单 turn 开销 = 10 × 50 × 0.1ms = 50ms → 可接受

高风险场景：
- 100+ events/turn（大量工具调用）→ fold 可能 > 500ms
- 解决方案：checkpoint + tail replay（DSH 模式）
  - 每 100 events 写一次 projection checkpoint
  - fold 时从最近 checkpoint 开始，只 replay tail
  - checkpoint 写入与 fold 异步（不影响 append 延迟）
```

#### Journal 写入吞吐

```
单条 append 延迟 = EventScope 填充 + freeze + persistence.write + projector notification

典型值：
- EventScope 填充：< 0.01ms（从 contextvars 读取）
- freeze + 序列化：< 0.05ms
- JSONL write（fsync=false）：< 0.1ms
- projector notification：< 0.5ms（5 个 projector 各 fold 一次）
- 总延迟：< 1ms/append → 可接受

高风险场景：
- 并发 append > 100/s → JSONL write 可能成为瓶颈
- 解决方案：write buffer + periodic flush（batch 10 events, flush every 10ms）
```

### 8.2 错误传播与 Plugin 故障域

```
Plugin 故障分类：

1. reconcile 阶段故障
   - 某个 plugin 加载失败 → Loader 标记 handle 状态为 FAILED
   - 依赖它的 plugin → 级联标记为 FAILED
   - 不依赖它的 plugin → 正常 ACTIVE
   - 如果关键 seam（如 llm、sessions）无 provider → Loader 拒绝启动

2. 运行期故障
   - Plugin service 方法抛异常 → 由调用方 try/except 处理
   - Plugin middleware 抛异常 → MiddlewareRegistry 记录错误，跳过该 middleware，继续执行链
   - Plugin 内存泄漏 → ScopedPluginHost.drain() 释放所有 effect，scope 销毁时清理引用

3. 热替换故障
   - hot_safe plugin 替换失败 → 保留旧版本实例，记录错误
   - restart_scope plugin 替换失败 → scope drain 失败时强制终止 scope 内所有 agent
   - 回滚机制：config rollback（Loader 已实现）

级联规则：
   - parent scope unload → 所有 child scope drain → 所有 child scope 内 agent cancel
   - agent cancel 是 graceful 的：等待当前 step 完成，不中断正在执行的 LLM 调用
   - 如果 graceful cancel 超时（30s），强制 kill
```

### 8.3 Harness 层自身的可观测性

**决策**：harness 层（kernel, session, agent, projection, command）自身的可观测性由以下 plugin 提供：

| 关注点 | Plugin | 实现 |
|---|---|---|
| Plugin lifecycle 事件 | `observability.lifecycle` | `PluginHost` emit event on reconcile/drain → journal |
| Scope 创建/销毁 | `observability.scope` | `ScopedPluginHost.fork()/drain()` emit event |
| Middleware 执行耗时 | `observability.middleware` | `MiddlewareRegistry.run()` 记录每个 middleware 的 duration |
| Projection fold 延迟 | `observability.projection` | `ProjectionRegistry` 记录 fold lag（current_seq - projection.as_of_seq）|
| Journal 写入延迟 | `observability.journal` | `SessionStore.append()` 记录 write latency |
| Command 处理耗时 | `observability.command` | `CommandGateway` 记录每个 command 的 processing time |

这些 plugin 在 `bundles/observability.yaml` 中声明，默认包含在所有 profile 中。

### 8.4 测试策略补充

除了 §5.1 测试金字塔，增加以下守卫测试：

```python
# tests/harness/test_architecture_self_consistency.py
async def test_no_hardcoded_capabilities_in_runtime():
    """CognitiveRuntime 不 import 任何 policy/hook/log 模块"""
    # 检查 CognitiveRuntime 的 import 图不包含 policy/hook/log
    ...

async def test_gateway_import_boundary():
    """CommandGateway 只 import contracts/harness/command + projection + session"""
    # 检查 gateway.py 的 import 不包含 agent/layer1/layer2/layer3
    ...

async def test_all_capabilities_are_plugins():
    """boot_capabilities 中每个 mount 都有对应的 plugin module"""
    # 检查 plugin tree 覆盖了所有 capability
    ...

async def test_seam_completeness_via_loader():
    """Loader reconcile 校验 seam 完整性——等价于原 require_complete()"""
    ...

async def test_concurrent_append_seq_monotonic():
    """并发 append 的 seq 单调递增无间隙"""
    ...
```

## 9. 未纳入当前 Phase 的 DSH 子系统清单（暂不实施，备忘）

> 本节逐个记录 `~/deepseek-harness/packages/` 和 `~/deepseek-harness/docs/subsystems/` 中存在、但本 spec 当前版本未详细设计的子系统。
> 目的：做到 Phase D/E 时不再需要重新对照 DSH 源码。每一项标注了对 LCA 的相关性等级和一句话处理建议。
> **不阻塞 Phase A–C 的执行。**

### 9.1 LLM 全栈（5 包）

DSH 包：`llm/llm`、`llm/llm-deepseek`、`llm/llm-pi-ai`、`llm/llm-retry`、`llm/token-meter`

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **LLM 核心协议** | `llm/llm`：Message/StreamChunk/ContentBlock/ToolSchema/GenerateOptions/PreparedLlmCall，assembler（流式块拼装），retry-policy，adapter-failure 分类，call-config 冻结语义，attribution（provider/model 溯源） | §2.2.1 `lca.llm.service` 基本覆盖 | 现有 `LlmService` 已有此模式，Phase A 接入即可 |
| **多 Provider Adapter** | `llm-deepseek`（SSE 流式 + translate）、`llm-pi-ai`（catalog + discovery + context + replay + stream）：每个 provider 是独立 Cordis plugin，通过 `prepareCall()` 协议可 override config（adapterDefaults） | spec 只写了 `ProviderMode.REGISTRY` | Phase E 需要：每个 LLM provider 拆为独立 plugin module，实现 `prepareCall()` → `PreparedLlmCall` 协议 |
| **Retry 策略** | `llm-retry`：transport recovery + exponential backoff + history tracking，独立于 agent-loop 的 plugin | 未提及 | **建议纳入 Phase E**：作为 `agent.request_error` middleware 实现，与 `llm-retry` 等价 |
| **Token Meter** | `llm/token-meter`：session projection，surface-fold（按 surface 节点统计 token）、usage-projection（per-model/per-provider 用量）、breakdown-projection（per-section 上下文 token 分布） | 未提及 | **建议纳入 Phase E**：作为 3 个 ProjectionDefinition 实现，驱动 `bundles/observability.yaml` |

### 9.2 Compaction 子系统（4 包）

DSH 包：`compaction/compaction`（Definition）、`compaction/compaction-basic`（Provider）、`compaction/compaction-tool-result-pruner`（裁剪策略）、`compaction/command-compact`（Consumer）

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **Capability Seam 三件套** | Definition（`ctx.compaction`）+ Provider（`compaction-basic`，tokenizer/template 可替换后端）+ Consumer（`command-compact`，人类命令触发） | §3.6.2 提到 SurfaceOp replace 用于 compaction；§4 Phase E 提了一句 | 需要拆为 3 个 plugin module：`seam_compaction`（DEFINITION）、`compaction_basic`（PROVIDER）、`command_compact`（CONSUMER） |
| **Compaction 事件词表** | `compaction/start`（获取锁）→ `compaction/summary`（安全摘要投影 + LLM 调用 envelope + shadowed range/seqs/token count）→ `compaction/end`（释放锁）；全部 log-only，不扩展 SurfaceEventType | 未定义 | 需要对应的 3 个 `@session_event` 装饰器 |
| **Tool Result Pruner** | 独立 plugin，在 compaction 前裁剪过大的 tool/result 事件，减少摘要输入 | 未提及 | **建议作为 compaction_basic 的内部策略**，不作为独立 seam |
| **Crash-orphaned Lock 恢复** | unmatched `compaction/start`（无对应 end）在 resume 时检测并清理 | 未提及 | SessionStore resume 时需要处理 |

### 9.3 Context 动态注入子系统（4 包）

DSH 包：`context/agent-instructions`、`context/session-reference`、`context/time-context`、`context/tmux-context`

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **Prompt Section 注册机制** | 每个 context plugin 通过 `ctx.systemPrompt.section()` 向 prompt 注册命名 section，带 order 优先级 | §3.5 提到 prompt assembly service，但没设计 section 注册协议 | **高优先级**：需要在 `systemPrompt` service 上增加 `register_section(key, renderer, order)` 接口 |
| **AGENTS.md 注入** | `agent-instructions`：读取 cwd 及父目录的 AGENTS.md 文件，作为 prompt section 注入；digest 追踪变更 | 未提及 | **建议 Phase E**：LCA 的 roles/ 目录已有类似概念，可映射为 section provider |
| **跨 Session 引用** | `session-reference`：URI scheme（`session://<id>/...`）引用其他 session 的内容，projection 追踪 | 未提及 | **中优先级**：多 agent 协作场景需要，Phase D subagent 完成后考虑 |
| **时间上下文** | `time-context`：时区感知的日期/时间注入，request-zone 计算 | 未提及 | **低优先级**：structlog 已有时间戳，可按需添加 |
| **终端状态注入** | `tmux-context`：捕获 tmux pane 内容注入 prompt | 未提及 | **不做**：LCA 不是 coding agent |

### 9.4 Goal 目标追踪子系统（3 包）

DSH 包：`goal/goal`、`goal/tool-goal`、`goal/command-goal`

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **事件溯源目标** | `GoalRef { id, revision }`（CAS revision），`GoalSnapshot { objective, phase, blockReason? }`，`GoalPhase = active \| paused \| blocked \| complete` | 未提及 | **建议 Phase E**：LCA 的 Task/Project 管理可借鉴此模式；作为 session projection 实现 |
| **Goal 工具** | `set_goal` / `update_goal` / `complete_goal` 等工具，模型可主动管理目标 | 未提及 | 需要对应的 tool plugin |
| **Goal Projection** | `foldGoal(events)` → 最新 GoalSnapshot，纯函数 fold | 未提及 | ProjectionDefinition 实现 |

### 9.5 Plan Mode 规划模式子系统（2 包）

DSH 包：`plan/plan-mode`、`plan/tool-exit-plan-mode`

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **软引导模式** | `plan/mode` log-only 事件（whole-value replace），`foldPlanMode(events)` 恢复状态；active 时注入 `plan:policy` prompt section | 未提及 | **中优先级**：LCA 可以有等价的「规划模式」，作为 policy plugin 实现 |
| **Exit 工具** | `exit_plan_mode` tool：要求模型输出完整 markdown plan，通过 user-questions seam 让用户审批 | 未提及 | 需要 interaction seam（§9.7）先就位 |
| **/plan 命令** | `/plan [off\|message]`：裸 `/plan` 进入模式，`/plan off` 退出，`/plan <msg>` 进入并 steer | 未提及 | LCA 的命令系统需要等价能力 |

### 9.6 Schedule 会话内调度子系统（2 包）

DSH 包：`schedule/schedule`、`schedule/tool-schedule`

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **持久提醒** | 三种变体：`AfterScheduleRecord`（延迟）、`AtScheduleRecord`（绝对时间）、`EveryScheduleRecord`（固定间隔，≥5min）；全部 session-local，durable | 未提及 | **中优先级**：LCA 的 cron/定时场景可用，作为独立 schedule plugin |
| **会话内投递** | 到时间后作为新 turn 的 user/message 投递到原 session | 未提及 | Inbox.followup() 已支持 |

### 9.7 Interaction 用户交互子系统

DSH 包：`interaction/`（user-questions seam + approval seam）

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **User Questions** | 统一的「向用户提问」seam：模型通过 tool 发起问题，通过 interaction channel 呈现给用户，用户回答后 tool 返回 | §2.2.7 AnswerCommand/SteerCommand 覆盖了 HIL，但没设计「模型主动提问」的 seam | **高优先级**：Plan Mode、HIL approval 都依赖此 seam |
| **Approval** | `tools.pre_execute` waterfall 中的 allow/deny/ask 决策，与 user-questions 联动 | §2.2.5 `tools.pre_execute` waterfall 覆盖了 | 已有，但需要与 user-questions seam 联动 |

### 9.8 Attachment 大内容管理

DSH 包：`attachment/`

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **ContentRef 抽象** | 大内容不内联在事件中，通过 `ContentRef` 引用外部存储 | §2.2.3 事件词表中有 `content_ref: str` 字段 | **高优先级**：需要设计 Attachment Store 后端（文件系统 / SQLite / S3） |
| **分块 + 去重 + 引用计数** | 内容按块存储，相同内容去重，引用计数管理生命周期 | 未提及 | Attachment Store 实现细节，Phase B 设计接口，Phase E 实现 |
| **Surface 引用** | `sourceEventSeqs` 追踪哪些 chunk 构建了哪个 message | §3.6.2 Surface 设计覆盖了 append 和 replace | 需要补充 sourceEventSeqs 到 SessionEvent |

### 9.9 Session 周边子系统（6 包）

| 包 | 作用 | Spec 状态 | LCA 处理建议 |
|---|---|---|---|
| `session-checkpoint-policy` | Crash recovery：per-request durability checkpoint，决定何时 fsync | 未提及 | **建议 Phase B**：在 SessionStore 的 persistence 层实现 checkpoint 策略 |
| `session-projection-cache` | Projection 持久化缓存：避免冷启动全量 replay | §8.1 提到 checkpoint + tail replay 但未设计 | **建议 Phase B**：ProjectionRegistry 需要 checkpoint 持久化 |
| `session-telemetry` | Redaction + telemetry coordinator | 现有 RunStore 已有 redaction | 保持现有机制，适配新 SessionEvent 格式 |
| `session-telemetry-otel` | OpenTelemetry 投影 | 现有 projectors 已支持 OTel | 保持现有机制 |
| `session-stats` | 统计 projection（event count, turn count, tool call count 等） | 未提及 | **低优先级**：作为 ProjectionDefinition 实现 |
| `session-title` | LLM 驱动的会话标题生成（3 种策略：first-prompt / all-prompts） | 未提及 | **低优先级**：UI 增强，作为 session projection + LLM consumer 实现 |
| `session-query` | 结构化 session 日志查询（不是原始遍历，是带索引的查询接口） | `SessionStore.read_from()` 只是顺序读取 | **中优先级**：当 session 日志量大时需要，Phase E 考虑 |

### 9.10 Workflow 工作流子系统（4 包）

DSH 包：`workflow/workflow`（Definition）、`workflow/workflow-worker-thread`（Provider）、`workflow/tool-workflow`（Consumer）、`workflow/tool-ralph`

| 子能力 | DSH 实现 | Spec 当前状态 | LCA 处理建议 |
|---|---|---|---|
| **Workflow SPI** | `WorkflowStartRequest { script, meta, args, parent, signal }`：模型写脚本 → engine 执行；`WorkflowMeta { name, description, phases }` | §4 Phase E 提了 `workflow_dag` 名字，无 SPI | 需要完整 SPI 定义 |
| **Worker Thread 隔离** | Node `worker_threads`：每个 run 一个 worker，脚本的 vm context 在 worker 内 | 未提及 | Python 等价：`asyncio.Task` 隔离 或 `multiprocessing.Process` 隔离 |
| **Agent() / Phase() 脚本 API** | 脚本内 `agent()` 启动子代理，`phase()` 声明进度 | 未提及 | 需要 Python 版脚本 API |
| **Ralph Tool** | Agent 在 workflow 内协作的专用工具 | 未提及 | **暂不做** |

### 9.11 其他低相关性子系统

| DSH 子系统 | 包 | 作用 | LCA 处理建议 |
|---|---|---|---|
| **Feedback** | `feedback/` | 结构化用户反馈（thumbs up/down） | **暂不做**：LCA 的 InsightEngine 已有等价能力 |
| **Spill** | `spill/` | 长输出渐进式释放 | **不做** |
| **LSP** | `lsp/` | Language Server Protocol 集成 | **不做**：coding agent 专用 |
| **Code Runtime** | `code-runtime/` | 代码执行沙箱类型系统 | **暂不做**：LCA 的 sandbox 用不同方案 |
| **Terminal** | `terminal/` | PTY 终端管理 | **不做**：coding agent 专用 |
| **Subprocess** | `subprocess/` | 子进程生命周期管理 | **暂不做**：LCA 用 asyncio subprocess |
| **Credentials** | `credentials/` | API key 安全存储和注入 | **已有**：LCA 的 pydantic-settings + 环境变量 |
| **Identity** | `identity/` | 用户身份识别 | **已有**：LCA 的 user/auth 系统 |
| **Typert** | `typert/` | DI 类型安全协议注册 | **已有**：Python Protocol + 注册表替代 |
| **Settings** | `settings/` | Plugin-scoped 配置覆盖 | **已有**：`PluginManifest.config_model` + pydantic |
| **Storage** | `storage/` | 域对象持久化抽象 | **中优先级**：当 LCA 需要域对象存储时考虑 |
| **Extensions** | `extensions/` | Tool/Command/Prompt section 高层注册 API | **Phase A**：通过 PluginManifest + middleware 覆盖 |
| **Runtime Diagnostics** | `runtime-diagnostics/invariants/` | 运行期不变量检查 | **建议 Phase B**：在 SessionStore/AgentRegistry 内置 invariant 检查 |

### 9.12 结构性模式差距汇总

以下不是缺某个包，而是 DSH 有但 Spec 没有的**结构性模式**：

| 模式 | DSH 做法 | Spec 差距 | 建议时机 |
|---|---|---|---|
| **Capability Seam 三件套拆分** | 每个非 spine 能力都拆为 Definition + Provider + Consumer 独立包 | §3.7 把 Seam 融入了 PluginManifest，但没有为每个扩展能力拆出独立 plugin module | Phase E：为 compaction、workflow、goal 等拆分 |
| **prepareCall 协议** | LLM adapter 可通过 `prepareCall()` override config（adapterDefaults），agent-loop 据此调整 reasoning effort / max tokens | 未设计 | Phase E：LLM provider 拆分时一并实现 |
| **Session Projection 生态** | 6+ 个独立 projection（conversation / activity / status / token-usage / breakdown / title / stats） | §2.2.6 定义了 ProjectionDefinition SPI，但没有列出 LCA 需要的具体 projection 清单 | Phase B 末尾：列出第一批 projection |
| **Dynamic Context Provider 注册** | context plugin 通过 `ctx.systemPrompt.section()` 注册命名 section | 未设计 section 注册协议 | Phase E：system-prompt 插件化时实现 |
| **ContentRef + Attachment Store** | 大内容走外部存储，事件只存引用 | 事件词表有 `content_ref` 字段但无存储后端设计 | Phase B：定义 AttachmentStore Protocol |

### 9.13 相关性速查矩阵

```
相关性     子系统                               建议 Phase
─────────────────────────────────────────────────────────
🔴 高     Prompt Section 注册协议               E
🔴 高     Attachment Store（ContentRef 后端）    B
🔴 高     User Questions seam                   E
🟡 中     Compaction（上下文压缩）               E
🟡 中     Workflow engine                       E
🟡 中     LLM retry middleware                  E
🟡 中     Token meter projections               E
🟡 中     Goal tracking                         E
🟡 中     Plan mode                             E
🟡 中     Schedule（会话内调度）                 E
🟡 中     Session checkpoint policy             B
🟡 中     Session projection cache              B
🟡 中     Session query                         E
🟡 中     Runtime diagnostics invariants        B
🟢 低     Session title                         —
🟢 低     Session stats                         —
🟢 低     Time context                          —
⚫ 不做   LSP / Terminal / Spill / Code Runtime  —
```

---

## 附录：关键代码对照

### A. 旧 vs 新：创建 Agent

```python
# 旧
composer = AgentComposer()
agent = composer.compose(spec)
result = await agent.run(question, run_ctx)

# 新
receipt = await command_gateway.handle_create_session(
    SessionCreateCommand(idempotency_key="...", profile="web-standard")
)
receipt = await command_gateway.handle_send_message(
    MessageSendCommand(idempotency_key="...", session_id=receipt.session_id, content=question)
)
snapshot = await command_gateway.get_snapshot(receipt.session_id)
```

### B. 旧 vs 新：HIL Resume

```python
# 旧
session = registry.get(run_id)
result = await session.runnable.resume(session.snapshot, input=answer)

# 新
receipt = await command_gateway.handle_answer(
    AnswerCommand(session_id=session_id, answer=answer)
)
# 进程重启后也能恢复——AgentRegistry.resume() 从 durable session 恢复
```

### C. 旧 vs 新：DSH 执行

```python
# 旧
if is_dsh_driver(session.execution_target):
    await execute_dsh_session(session)
else:
    runnable = build_solo_agent(...)

# 新 — profile 决定
# profiles/dsh-standard.yaml
# patch:
#   - id: agent-loop
#     config: { provider: lca.loop.dsh_bridge }
# Gateway 无分支
```

### D. 完整 Plugin 示例：Seam Definition + Provider + Consumer

```python
# ── DEFINITION：定义扩展点 ──
# lca/plugins/seam_llm/__init__.py
manifest = PluginManifest(
    id="lca.seam.llm",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.DEFINITION,
    seam_key="llm",
    extension_points=(
        ExtensionPoint(
            seam_key="llm",
            dispatch_mode="waterfall",
            description="LLM adapter: 接受 LLMRequest，返回 LLMResponse",
        ),
    ),
)

# ── PROVIDER：实现扩展点 ──
# lca/plugins/llm_deepseek/__init__.py
manifest = PluginManifest(
    id="lca.llm.deepseek",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.PROVIDER,
    seam_key="llm",
    provides=("llm.provider.deepseek",),
    provider_mode=ProviderMode.REGISTRY,  # 多 LLM provider 共存
)

async def apply(ctx: PluginContext, config: dict) -> None:
    from lca.infrastructure.llm_adapter.deepseek import DeepSeekAdapter
    adapter = DeepSeekAdapter(
        api_key=config["api_key"],
        model=config.get("model", "deepseek-chat"),
    )
    ctx.mount("llm.provider.deepseek", adapter)

# ── CONSUMER：使用扩展点 ──
# lca/plugins/loop_cognitive/__init__.py
manifest = PluginManifest(
    id="lca.loop.cognitive",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.CONSUMER,
    seam_key="llm",
    requires=("llm",),
    middleware=(
        "agent.before_perceive",
        "agent.after_perceive",
        "agent.before_think",
        "agent.after_think",
        "agent.before_act",
        "agent.after_act",
        "agent.before_reflect",
        "agent.after_reflect",
        "agent.before_turn_end",
    ),
)
```

### E. Middleware Waterfall 协议详解

```python
# ── Waterfall 执行模型 ──
#
# 注册 middleware（按 priority 排序）：
#   priority=10: budget_check
#   priority=50: content_filter
#   priority=90: logging
#
# waterfall 执行（前一个输出 = 后一个输入）：
#
#   input ──→ [budget_check] ──→ modified_state ──→ [content_filter] ──→ ... ──→ [logging] ──→ output
#
# 如果任何 middleware 抛异常 → 链终止，异常传播到调用方
# 如果 middleware 返回 None → 视为"放行"，传递当前 state 不变

async def run_waterfall(seam_key, phase, state, context):
    middlewares = sorted(
        registry.list_registrations(seam_key),
        key=lambda r: r.priority,
    )
    current = state
    for reg in middlewares:
        mw = registry.get_middleware(reg)
        try:
            result = await mw(phase, current, context)
            if result is not None:
                current = result
        except MiddlewareAbort as e:
            _log.warning("middleware_abort", seam_key=seam_key, plugin=reg.plugin_id, error=str(e))
            raise
        except Exception as e:
            _log.error("middleware_error", seam_key=seam_key, plugin=reg.plugin_id, error=str(e))
            # 非 abort 异常 → 跳过该 middleware，继续执行链
    return current

# ── Around 执行模型（洋葱模型）──
#
# 注册 middleware（按 priority 排序，外层 priority 小）：
#   priority=10: auth_check      （最外层）
#   priority=50: timeout_guard   （中间层）
#   priority=90: retry_guard     （最内层）
#
# around 执行：
#
#   auth_check(                          # 进入
#     timeout_guard(                     # 进入
#       retry_guard(                     # 进入
#         actual_tool_execution()        # 核心
#       )                                # 退出
#     )                                  # 退出
#   )                                    # 退出

# ── Serial 执行模型 ──
#
# 所有 middleware 收到相同输入，结果收集为 list
# 用于 notification 场景（before_turn_end 等）
#
#   input ──→ [mw1] → result1
#   input ──→ [mw2] → result2
#   input ──→ [mw3] → result3
#   收集 → [result1, result2, result3]
```

### F. Scope 层级与 Plugin 可见性矩阵

```
Scope 层级               典型 plugin 可见性
─────────────────────────────────────────────────
Deployment               全局服务（LLM 连接池、FileStore）
  └─ Profile             部署级配置（哪些 bundle 激活）
      └─ Team            团队级覆盖（特定 team 的 LLM provider）
          └─ Agent       Agent 级覆盖（特定 agent 的 tool filter）
              └─ Session Run 级覆盖（几乎不用，预留扩展）

规则：
- 低层级可以 shadow 高层级同名服务（nearest-layer-wins）
- 低层级不能向高层级 publish 新服务
- 高层级 unload → 低层级 cascade drain
- Plugin 在 manifest.scopes 声明它活跃在哪些层级
```

### G. 自洽性 Checklist

在 spec 实现完成后，逐项检验：

- [ ] `boot_capabilities()` 已删除或标记 `@deprecated` 且无新调用方
- [ ] `register_seam_catalog()` 已删除或标记 `@deprecated`
- [ ] Gateway 不 import `layer1_*`、`layer2_*`、`layer3_*`、`contracts/harness/agent.py`
- [ ] CognitiveRuntime 源码不含硬编码的 hook/log/journal.append 调用
- [ ] 每个 capability 都有对应的 plugin module（DEFINITION/PROVIDER/CONSUMER）
- [ ] Loader reconcile 通过 seam completeness check
- [ ] ScopedPluginHost.current() 在任何 plugin 代码中可用
- [ ] 替换 loop provider（CognitiveLoopFactory → ReplayLoopFactory）不改 Gateway
- [ ] 替换 LLM provider（deepseek → mock）只改 profile YAML
- [ ] 进程重启后 from journal + checkpoint 恢复 session
- [ ] 所有横切关注点（budget、loop intervention、skill activation）由 plugin middleware 实现
