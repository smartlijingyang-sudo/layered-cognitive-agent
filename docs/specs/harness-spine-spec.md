# LCA Harness Spine Spec：从第一原理到可执行重构

**版本：v1.1-draft（评审修订版）**
**基于: main @ `8e552cc` 实际代码**
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
│   ├── loop_replay/                 # Deterministic replay loop
│   ├── gateway_starlette/           # HTTP/SSE carrier plugin
│   ├── session_jsonl/               # JSONL persistence plugin
│   ├── projections_web/             # conversation/activity/status/skills projections
│   ├── skills_filesystem/           # Disk skill store as provider
│   ├── tool_skill/                  # skill(name) tool
│   ├── subagent_inprocess/          # In-process child agent provider
│   ├── subagent_team/               # Team composer as subagent provider
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
├── profiles/                        # deployment & agent profiles
│   ├── web-standard.yaml            # 默认部署 profile
│   ├── solo-cognitive.yaml          # 单 agent 认知
│   ├── team-research.yaml           # 团队研究
│   └── creator.yaml                 # 开发者工具
├── presets/                         # agent presets
│   ├── researcher/profile.yaml      # extends: web-standard + plan_graph loop
│   └── coder/profile.yaml           # extends: web-standard
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
    对应 waterfall/serial event name，对应 LCA 原 Seam Definition。
    
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
# The Session plane carries NO tool lifecycle vocabulary. Tool facts are owned
# by the Journal plane (ToolStarted / ToolInvoked / ToolDenied, joined by
# invocation_id — ADR-0101 PR-2) and surfaced through LoopCursor step records
# (step.tool_call.record / step.tool_result.record). Adding tool.*.v1 session
# events would create a second SSOT for the same fact; resume/approval durable
# points use approval.persisted.v1 / approval.resolved.v1 below instead.

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
    对应 waterfall 中间件。
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
    supported_providers: tuple[str, ...] = ()    # "inprocess", "a2a"

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

# ── Async scope 传递 ──
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
        """层级解析：先查自己，再查 parent(nearest-layer-wins)"""
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
        在 async task 中自动传递 scope —— Python 等价于 fiber-scoped Context。
        
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
    await session_store.append(ApprovalResolved(
        approval_id=cmd.approval_id,
        command_id=cmd.command_id,
        payload=cmd.answer,
        approved=True,
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

## 7. 最终验收标准

| 问题 | 达标标准 |
|---|---|
| 换模型/sandbox/memory/loop 是否需要改 Gateway/Composer 源码？ | 否；Profile/Preset binding 改动即可 |
| 前端发一个消息是否直接调用某个 Python Agent 类？ | 不会；前端只提交 command |
| 前端状态是否由 raw token/event 猜测？ | 不会；由 server-side projection 提供 |
| 模型上下文是否能完全重建？ | 能；每一段都有 durable event/source reference |
| 现有认知闭环和 Team 优势是否仍在？ | 在；它们分别是 default loop 和 team provider |

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
- 解决方案:checkpoint + tail replay
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

# Gateway 无分支,driver 选择由 `agent_loop.select(execution_target)` 完成(参见 [ADR-0120](0120-retire-dsh-driver.md))
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
