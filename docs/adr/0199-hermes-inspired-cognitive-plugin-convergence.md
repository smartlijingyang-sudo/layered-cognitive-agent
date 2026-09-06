# ADR-0199 — Hermes 启发的认知插件架构收敛

## 状态

**Proposed**（2026-09-06）。**Phase 0（本 ADR 冻结）已完成**；**Phase 1（Runtime Facade + RunIntent 契约）已批准进入实现**。

**延伸并统摄**：[ADR-0061](0061-plugin-manifest-resolve-boot.md)（Resolve/Boot）、[ADR-0068](0068-compiled-plugin-kernel-and-unified-run-plan.md)（CompiledRunPlan）、[ADR-0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md)（PhaseGraph）、[ADR-0115](0115-kernel-transport-boundary.md)（Kernel/Transport）、[ADR-0183](0183-event-bus-framework-ssot.md) / [ADR-0186](0186-session-as-event-ssot.md)（事实平面）、[ADR-0194](0194-cognitive-loop-architecture-convergence.md)（Loop 收敛）、[ADR-0195](0195-platform-architecture-convergence.md)（平台三时态）、[ADR-0197](0197-guard-stack-hermes-dsh-convergence.md)（Guard Stack）、[ADR-0198](0198-observability-compile-graph.md)（观测 compile graph）。

**本文档角色**：在 ADR-0195 平台壳之上，回答 **「如何从 Hermes 已验证的工程能力中择优吸纳，而不牺牲 LCA 编译闭包、认知图与事实单轨」**。0194/0195 解决 Loop 与 Observability 收敛；0199 解决 **入口统一、插件治理、分域注册与诊断闭环**。

---

## 0. 决策摘要

LCA **不复制** Hermes 的中心化工具注册表或单一 Agent Loop。LCA **保留并强化**：

- 声明式依赖图与 bundle DAG（K1 resolve）
- 不可变 `CompiledRunPlan` + `plan_ref`（K2 compile）
- 六语义 phase 图与 `PhaseGraph` 解释器（C1 闭集）
- `FactGateway → Session.append` 事实单轨（ADR-0194/0195）
- 分层 import 法与 `AuditedPluginContext`（UndeclaredInteractionError）

LCA **吸收** Hermes 已验证的四项工程能力：

| 能力 | Hermes 来源 | LCA 落点 |
|---|---|---|
| 统一运行时 Facade | `AIAgent` 服务 CLI/Gateway/Cron/ACP/Batch | `RuntimeFacade` + `RunIntent`（contracts 层） |
| Manifest 与能力声明 | `plugin.yaml` + `register(ctx)` | 强化 `@plugin` / `PluginSpec` 为唯一可审计来源 |
| 显式 enable / trust / consent | bundled < user < project(opt-in) < pip | `PluginOrigin` + `privileges` + Profile provenance |
| Plugin Doctor | `hermes plugins doctor` 走真实 runtime | `lca.harness.diagnostics.doctor` = compile dry-run + 只读 projection |

**终态一句话**：

> **Surface → Runtime Facade → Cognitive Plan Interpreter → Capability Ports → Plugins → Event/Projection Plane**

所有入口（Web、CLI、批处理、Gateway、测试、未来 IDE/消息平台）只负责把外部刺激转换为统一的 **`RunIntent`**。入口不得自行组 prompt、选 provider、拼插件、写 journal 或解释阶段图。运行时只消费启动阶段生成的不可变 **`CompiledRunPlan`**；插件只通过声明的 capability、privilege 与事件协议交互。

---

## 1. 第一性原理

### 1.1 Agent 的最小职责

长期可维护的 Agent 不是工具集合，而是 **受约束的状态转移系统**：

```text
输入事实 → 认知状态 → 计划/决策 → 受控副作用 → 新事实 → 状态归约 → 投影/诊断
         └──────────────── 三时态边界（ADR-0195 §1.1）────────────────┘
              Compile-time          Run-time              Observe-time
```

因此代码结构必须围绕 **四类不可替代的事实** 组织；任何绕开它们的平行配置、隐式全局注册、运行期动态拼装或直接写持久化，都会制造不可回放、不可诊断和不可安全升级的分叉。

| 事实类别 | LCA 权威载体 | 设计要求 |
|---|---|---|
| 能力与依赖 | `PluginSpec` / `PluginContract` / Bundle DAG | 只声明，运行期不得猜测或补注册 |
| 当前运行闭包 | `CompiledRunPlan` + `plan_ref` | immutable、可 hash、可回放、可绑定 session |
| 认知顺序 | `CognitivePhaseGraphPlan` | 编译期验证（PG-* / PS-*），运行期解释 |
| 历史与观测 | `Session.append` → durable spine → fold | 单写入路径；投影不得反写事实 |

### 1.2 为什么不照搬 Hermes 的中心 Registry

Hermes `tools/registry.py` 在 import 时自注册 70+ 工具，对 **工具发现与分发** 极有效。但 LCA 插件不仅是 tool，还包括：

- 认知 phase executor、Gate 贡献、effect handler
- transport carrier、memory backend、guard、observability deriver
- 图拓扑、recovery 策略、convergence policy

把它们压成 **单一 registry** 会丢失：依赖方向、权限边界、认知语义、compile-time 验证。

**决策**：采用 **分域 Registry + 统一 Discovery Protocol** —— 每个域拥有自己的 typed registry；启动编译器（K2）将它们 **投影** 为一份 `CompiledRunPlan`。既获得 Hermes 的可发现性，又不牺牲 LCA 的领域边界。

### 1.3 Hermes 对标：采纳与不采纳

| Hermes 做法 | LCA 当前 | 决策 | 落地方式 |
|---|---|---|---|
| 多入口复用 `AIAgent` | 有 kernel/harness/transport，入口仍有历史分叉 | **采用** | `RuntimeFacade`；transport `RunRequest` 降为 L0 wire adapter |
| manifest 声明 tools/hooks/capabilities | 有 `@plugin`、`PluginSpec`、bundle DAG | **强化** | manifest 为唯一可审计来源；禁止运行期补注册 |
| 插件显式 enabled/disabled | bundle/profile 控制组合 | **采用** | `enabled`/`disabled`/`requires`/`provides`/`privileges` 进 ProfileResolution |
| Plugin Doctor | 有 arch checks + transport doctor + `lca-ops` | **合并** | 统一只读 doctor facade；复用 compile validators，不复制规则 |
| hook 生命周期 | EventBus hooks + event catalog | **采用但改名** | plugin hook → typed event 或 guard middleware；禁止任意旁路回调 |
| skills 作为可发现内容包 | skill plugins、roles、prompt catalog | **采用** | 内容型扩展与可执行插件分离；namespaced resource ID |
| model/provider/memory 后端可插拔 | llm、memory、state、transport capability | **强化** | 同一 capability **单活跃 provider** + 显式 `replaces` |
| 项目级插件默认关闭 | bundle/profile 可表达但安全语义分散 | **采用** | 非可信来源默认 disabled；启用须留 profile provenance |
| 兼容旧 import 的有限迁移期 | legacy/blacklist/迁移脚本 | **采用** | 到期日 + doctor warning + CI fail-close；不永久 shim |
| 进程内插件执行 | LCA 插件通常进程内 | **保留并分级** | trusted core vs untrusted external（MCP/沙箱/worker） |
| 单一同步 Agent Loop | LCA 阶段图 + 事件驱动控制面 | **不采用** | `PhaseGraph Interpreter` 保持可替换、可回放 |
| import-time tool self-register | 编译期不可验证 | **不采用** | compile-time `PluginSpec` + `@plugin` audited setup |
| AIAgent 20+ mixin 堆叠 | Cordis fiber + plan-bound DI | **不采用** | Facade 只编排；按 port 拆 adapter |

---

## 2. 目标架构

### 2.1 五层边界（L0–L4）

```text
L0  Surface
      CLI / HTTP / Gateway / Batch / IDE / Test harness
            ↓ RunIntent（contracts 层意图）
L1  Runtime Facade
      profile selection · session resolution · plan lookup · run dispatch · callbacks
            ↓ SessionActivation { plan_ref, graph_ref, plugin_set_ref, session_id, trust }
L2  Cognitive Interpreter
      perceive → think → act → reflect → remember → stop
      （Gate 为 Think 子链，非 graph node — ADR-0194）
            ↓ typed capability ports
L3  Capability Providers
      llm / tools / memory / transport / guards / observability / persistence
            ↓ events + immutable effect receipts
L4  Fact and Projection Plane
      FactGateway → Session.append → persistence → fold → doctor / UI / replay
```

**依赖法则**（对齐 ADR-0195 §1.2）：

| 层 | 不得 |
|---|---|
| L0 | 依赖 L2–L4 实现；不得 append journal；不得解释 phase graph |
| L1 | 包含具体 provider 逻辑；不得运行期修改 plan |
| L2 | import transport、DB 或具体 plugin 实现 |
| L3 | 绕过 `CommandEnvelope` / SafeExecutor 写世界 |
| L4 | 反向调用认知层或触发控制面副作用（C7） |

### 2.2 核心运行时对象

#### 2.2.1 `RunIntent`（contracts 层，L1 输入）

比 transport 层 `RunRequest`（`terminal/port.py`）更抽象，不含 Starlette/HTTP 字段，不携带 live `ctx` 对象引用作为权威来源。

```python
# 契约草案 — 实现落于 lca/contracts/runtime/intent.py
@dataclass(frozen=True)
class RunIntent:
    profile_path: str
    user_text: str
    mode: str                          # solo | team | ...
    session_id: str | None             # None ⇒ 新 session
    assistant_id: str | None           # ADR-0187 可选绑定
    attachment_ids: tuple[str, ...]
    prior_turns: tuple[ConversationTurn, ...]
    execution_target: str
    options: Mapping[str, Any]         # idempotency key 等（ADR-0163）
    surface: str                       # cli | http | gateway | test | batch
    device_id: str = ""
```

**规则**：L0 adapter 负责 wire → `RunIntent`；L1 `RuntimeFacade` 是唯一消费 `RunIntent` 并产出 `SessionActivation` 的公共入口。

#### 2.2.2 `SessionActivation`（运行期闭包句柄）

Hermes 以 SQLite session 行为 SSOT；LCA 以 **plan-bound activation** 为 SSOT。

```python
@dataclass(frozen=True)
class SessionActivation:
    activation_ref: str                # hash(plan_ref, graph_ref, plugin_set_ref, session_id)
    plan_ref: str
    graph_ref: str
    plugin_set_ref: str
    profile_path: str
    session_id: str
    trust_envelope: TrustEnvelope      # PluginOrigin + granted privileges
    compiled_plan: CompiledRunPlan     # 只读引用；运行期不可变
```

**规则**：所有 durable run event 必须携带 `activation_ref`（或等价三元组 `plan_ref`/`graph_ref`/`plugin_set_ref`）。Doctor、replay、failure attribution 均通过 activation 定位闭包。

#### 2.2.3 `RuntimeFacade`（L1 Port）

```python
class RuntimeFacade(Protocol):
    def resolve_activation(self, intent: RunIntent) -> SessionActivation: ...
    def dispatch_run(self, activation: SessionActivation) -> RunHandle: ...
    def dispatch_resume(self, activation: SessionActivation, ...) -> RunHandle: ...
```

**初始实现策略**：Phase 1 可作为 **adapter** 包装现有 `run_kernel` + `RunLifecycleCoordinator` + `CognitiveRuntime.run`，不改变旧入口签名；验收标准是同一 `RunIntent` 在 CLI、HTTP、测试入口生成相同 `plan_ref`。

### 2.3 分域 Registry 与 Unified Discovery Protocol

```text
CapabilityRegistry     ← llm, memory, tools, state_store, transport, guards, ...
PhaseRegistry          ← executors, topology, recovery, loop_guard_policy
EffectRegistry         ← handlers, EffectPolicyPlan projection
ResourceRegistry       ← skills, roles, prompts（只读内容）
EventRegistry          ← lca_kernel/events/config/*.yaml（已有 SSOT）
         │
         ▼  K2 compile（plan_compiler + phase_graph_compiler + capability_plan_resolver）
    CompiledRunPlan
         │
         ▼  K3 boot（AuditedPluginContext.setup）
    cordis.Context + SessionActivation
```

**Unified Discovery Protocol**（contracts Protocol，非全局 singleton）：

1. **Discover**：扫描 bundle entries + `@plugin` 模块（K1）
2. **Validate**：`PluginSpecValidator`、`PhaseGraphValidator`、capability cardinality、layer edges
3. **Compile**：投影为 immutable plan + hashes
4. **Activate**：K3 fiber setup；仅允许 manifest 声明的 `provide/require/register/emit`
5. **Observe**：lifecycle typed events（discover → validate → enable → setup → ready → degraded → shutdown → failed）

运行期 **禁止** 步骤 1–3 的隐式重复（无 fallback lookup、无 Context 猜插件）。

---

## 3. 插件契约 v2

现有 `@plugin` 与 `PluginSpec` / `PluginContract` 9 段保留。v2 在 **不破坏** ADR-0110 统一合约面的前提下，增加以下 **正交四维**（先由 `PluginSpec.meta` / `PluginContract` 扩展字段承载；全 provider 迁移后提升为强类型字段）。

### 3.1 四维契约

| 维度 | 含义 | 与 Hermes 对标 | 示例 |
|---|---|---|---|
| **provides** | 提供什么 capability | `provides_tools` / provider kind | `memory.semantic` |
| **requires** | 依赖什么 capability（非 Python import） | `requires_plugins`（advisory） | `state_store` |
| **privileges** | 被授权什么副作用（≠ provides） | `capabilities:` consent | `journal.append`, `network.egress` |
| **resources** | 分发的只读内容（不可隐式获执行权） | skills / Agent Plugins v1 | `skill:memory/retrieval` |

`effects` 是 privileges 在 Body 路径上的 **runtime projection**（经 `EffectPolicyPlan` + Guard stack — ADR-0197），不是第五套独立声明。

### 3.2 Manifest 示例（YAML 投影目标）

```yaml
id: lca.memory.semantic
api_version: lca-plugin/2
kind: provider
version: 1.2.0
origin:
  source: bundled          # bundled | project | user | pip
  trust: core              # core | trusted | untrusted
enabled_by: profiles/web-standard.yaml
requires:
  - state_store
provides:
  - memory.semantic
privileges:
  - state.read
  - state.write
lifecycle:
  setup: eager             # eager | lazy
  health: required
  shutdown: graceful
replaces: []               # 单活跃 provider 替换声明
resources:
  - skill:memory/retrieval
```

### 3.3 契约原则

1. **声明先于执行**：插件必须先 discover → validate → compile → enable → setup；运行期不得隐式改变 capability graph。
2. **能力而非模块依赖**：依赖 capability key，不依赖另一个插件的 Python import path（lint-imports 守护）。
3. **权限单独建模**：`provides` ≠ `privileges`；写 journal、执行 effect、访问网络必须显式声明并进入 Guard stack。
4. **生命周期可观察**：discover/validate/enable/setup/ready/degraded/shutdown/failed 产生 typed boot/run event。
5. **失败可归因**：加载失败须含 plugin id、phase、cause、remediation、`plan_ref`。
6. **版本可迁移**：`api_version`（契约）、`schema_version`（wire/persisted）、`version`（插件）分离；兼容层有明确 expiry。
7. **内容与执行分离**：skill/role/prompt 可随插件分发，不得通过资源扫描隐式注册可执行能力。

### 3.4 `PluginOrigin` 与信任模型

```python
@dataclass(frozen=True)
class PluginOrigin:
    source: Literal["bundled", "project", "user", "pip"]
    trust: Literal["core", "trusted", "untrusted"]
    enabled_by: str                    # profile/bundle path provenance
    discovered_at: str                 # absolute path or entry-point name（诊断用）
```

| source | 默认 trust | 默认 enabled |
|---|---|---|
| bundled（repo bundles） | core | profile 声明 |
| project（`.lca/plugins/` 等，命名待定） | untrusted | **false**；须 profile 显式 enable + provenance |
| user | trusted/untrusted | profile 声明 |
| pip entry point | untrusted | false；须 install + enable 审计 |

---

## 4. 认知图与 Hermes 长期融合

Hermes memory、skills、self-improving loop 可作为 LCA **外部能力**，但不得成为第二个隐式控制面。

```text
Memory facts ─┐
Tool results  ─┼→ Perception nodes → Cognitive graph → Decision nodes
Session events─┘                                  ↓
                                           Effect commands（CommandEnvelope）
                                                   ↓
                                           Receipts / durable events
```

| 外部能力 | 允许 | 禁止 |
|---|---|---|
| Memory | 提供带 provenance 的事实 **候选** | 直接改写 `AgentState` 或跳过 Gate |
| Skill | 提供可命名 prompt/策略 **资源** | 文本扫描 → 自动 tool 注册 |
| Self-improve | 生成 `PlanProposal` / review ticket | 热修改当前 active `CompiledRunPlan` |
| Hook（Hermes 式） | 转为 typed event 或 guard middleware | 旁路 FactGateway 写 journal |

**自我改进闭环**（受审计的计划演化）：

```text
Observe fold → PlanProposal → Profile Resolve → Graph Compile → Validation → Review/Approval → Activate(new plan_ref)
```

新 plan 激活前，旧 activation 上的 run 仍绑定旧 `plan_ref`；禁止运行期自修改。

---

## 5. Plugin Doctor 架构

### 5.1 设计原则（对标 Hermes，升级语义）

Hermes Doctor 的精髓：**走真实 PluginManager + registry，隔离环境，恢复全局状态**（`hermes_cli/plugin_dev.py`）。

LCA Doctor **不应**是第三套平行规则引擎，而应是：

```text
DoctorRequest(profile | plugin_path | run_id?)
    → resolve_profile (dry-run, no K3 side effects)
    → compile_run_plan
    → validate_phase_graph + PluginSpecValidator + capability cardinality
    → audit_plugin_shape + event registry consistency
    → optional: fold run facts → doctor.v3 hops（已有 webserver doctor）
    → DoctorReport { findings[], summary, activation_ref? }
```

### 5.2 `DoctorReport` 形状

每条 finding 必须具备：

| 字段 | 说明 |
|---|---|
| `code` | 稳定机器码（如 `DOC-PS-001`） |
| `severity` | error / warning / info |
| `owner` | ADR 或脚本 owner |
| `plugin_id` | 可空（profile 级 finding） |
| `remediation` | 人类可读修复指引 |
| `plan_ref` | 编译成功时填充 |

### 5.3 统一入口

| 消费者 | 入口 | 禁止 |
|---|---|---|
| CLI | `lca-ops doctor profile <path>` | 在 doctor 路径执行修复性副作用 |
| CI | `lca-ops doctor profile --ci --json` | 复制 Hermes socket-block 以外的平行 scanner |
| Web | 现有 `GET /runs/{id}/doctor` | 写 journal / 重启 kernel |
| Plugin 作者 | `lca-ops doctor plugin <path>` | 未声明网络访问的插件 doctor 仍 fail-closed on privilege |

**与 ADR-0198 关系**：run doctor 读 `CompiledObservabilityPlan`；profile/plugin doctor 读 `CompiledRunPlan` — 同一 compile pipeline，不同 projection。

---

## 6. 设计模式目录

| 模式 | 使用位置 | 解决问题 | 反模式（须清理） |
|---|---|---|---|
| **Facade** | `RuntimeFacade`, `FactGateway`, `run_kernel` | 消除入口与事实写入分叉 | transport 内 boot+run+fold |
| **Ports and Adapters** | contracts ↔ infrastructure；`RunRequest` → `RunIntent` | 认知域不依赖具体服务 | handler 直调 provider |
| **Interpreter** | `PhaseGraphPlan` 执行器 | 认知图 = 可验证数据 | imperative while-loop 隐式 phase |
| **Command** | `RunIntent`, `CommandEnvelope` | 意图与执行隔离 | Body 直写 world |
| **Memento** | `CompiledRunPlan`, `plan_ref`, `SessionActivation` | 快照可 hash、回放 | 运行期 mutating plan |
| **Specification** | `PluginSpecValidator`, `PhaseGraphValidator` | 编译期 fail-loud | 运行期 guess capability |
| **Builder** | `plan_compiler`, `phase_graph_compiler` | 复杂 plan 分步构建 | Composer 内联 new |
| **Strategy** | PhaseExecutor, Provider, Guard, Deriver | 可替换算法 | transport if/else 模式 |
| **Chain of Responsibility** | Guard stack（ADR-0197） | 统一 enforcement 顺序 | 散落 gates/effects |
| **Mediator** | `EnvelopeBus`, EventRegistry | 组件不直连 | spine_reflector 双写 |
| **Visitor** | FoldEngine, derivers | 投影遍历事实 | projection 反写事实 |
| **State** | Reducer, LoopCursor | 合法状态转移 | WritableMatrix 双写 |
| **Abstract Factory** | provider backend + `replaces` | 单活跃 provider 构造 | 隐式 default factory key |
| **Repository** | Session/Journal stores | 持久化隔离 | handler 直读写 spine |
| **Null Object** | no-op observability backend | 减少分支 | 用 null 藏错误 |
| **Template Method** | `PhaseExecutionTransaction`, K3 boot | 固定骨架、可变步骤 | phase 逻辑复制到 transport |

**刻意不用**：Hermes 式 **Service Locator**（全局 registry 到处 `get()`）。LCA 用 **plan-bound dependency injection**（Cordis Context + capability key）。

---

## 7. SSOT 矩阵扩展（相对 ADR-0195 §4）

| Concern | SSOT | 非 SSOT（须退役） |
|---|---|---|
| 运行入口意图 | `RunIntent` → `RuntimeFacade` | 各 surface 自行 resolve profile / boot |
| 运行闭包句柄 | `SessionActivation.activation_ref` | transport `RunRequest.ctx` 作 plan 来源 |
| 插件发现 | K1 resolve + `@plugin` | 运行期 Context 猜插件 |
| 插件权限 | `privileges` + `EffectPolicyPlan` | 散落 `effects`/`gates` 语义 |
| 只读内容 | `ResourceRegistry` namespaced ID | skill 扫描 → tool 注册 |
| 插件诊断 | `DoctorReport` from compile pipeline | 三套独立 doctor 规则 |
| 信任来源 | `PluginOrigin` | 混用 bundled/project 无 provenance |
| capability 命名 | `domain.subject[.variant]` | 无界短名称 |

---

## 8. 结构性债务清理

### 8.1 P0 — 单一真相风险（阻塞 Phase 1+）

| ID | 债务 | 处理 | delete-when |
|---|---|---|---|
| D-P0-1 | 旧 `PluginManifest` 与 `@plugin` 并存 | COMPAT 读取；禁止新引用 | `route_legacy_patterns.py` 零命中 + CI |
| D-P0-2 | EventBus / Session / Journal 重复授权写入 | EventRegistry + 单一 `FactGateway` commit seam | ADR-0194 acceptance + P-L7 |
| D-P0-3 | 运行期从 Context 动态猜插件或 plan | 只读启动产物；删 fallback lookup | grep `fallback.*plan` 仅测试 |
| D-P0-4 | 多套状态字面量与序列化 | 收敛 contracts enum + 唯一 `to_jsonable` | `audit_ssot_field_drift.py` 零 drift |
| D-P0-5 | sidecar/fold/preview 平行事实 | 统一 FoldEngine 投影 | 旁路写入 grep 为零 |

### 8.2 P1 — 可维护性风险

| ID | 债务 | 处理 |
|---|---|---|
| D-P1-1 | 大型 facade 与 mixin 式入口 | `RuntimeFacade` 只编排；按 port 拆 command/query/stream adapter |
| D-P1-2 | plugin 目录深层所有权不明 | 每 plugin：`README` + manifest + owner + test + capability list |
| D-P1-3 | capability key 无命名空间 | 强制 `domain.subject[.variant]`；shape audit 扩展 |
| D-P1-4 | bundled/project/user 来源混合 | 统一 `PluginOrigin` |
| D-P1-5 | Doctor 三处散落 | `lca.harness.diagnostics.doctor` 统一 facade |
| D-P1-6 | CLI vs `python -m lca_kernel serve` 双入口 | 均经 `RuntimeFacade` adapter |

### 8.3 P2 — 演进性风险

| ID | 债务 | 处理 |
|---|---|---|
| D-P2-1 | provider 无 replacement 语义 | `ReplacementDecision` + active backend selection（plan 已有字段） |
| D-P2-2 | run event 缺 plan/graph ref | 所有 durable EP 携带 `activation_ref` |
| D-P2-3 | 组合闭包测试不足 | profile doctor + minimal boot + replay + failure attribution 矩阵 |
| D-P2-4 | `@plugin` 三键 alias（ADR-0110） | 迁移窗口 + doctor warning + expiry |

---

## 9. 不变量

| ID | 不变量 | 要求 |
|---|---|---|
| **I-HPC-1** | 入口薄 | L0 只产 `RunIntent`；不得 append journal 或解释 phase graph |
| **I-HPC-2** | Plan 不可变 | 运行期 `CompiledRunPlan` 只读；变更须 recompile 新 `plan_ref` |
| **I-HPC-3** | Activation 绑定 | durable event 携带 `activation_ref` 或等价三元组 |
| **I-HPC-4** | 声明先于执行 | 运行期禁止隐式 plugin/capability 注册 |
| **I-HPC-5** | provides ≠ privileges | 未声明 privilege 的 effect 必须 fail-closed |
| **I-HPC-6** | 内容只读 | resource 不得隐式获得 execute 权限 |
| **I-HPC-7** | Doctor 只读 | doctor 路径禁止修复性副作用（C7） |
| **I-HPC-8** | Hook 不旁路 | plugin hook 仅 typed event 或 guard；禁止直写 Session |
| **I-HPC-9** | 分域 registry | 禁止单一 global tool registry 替代 compile projection |
| **I-HPC-10** | 自我改进受审计 | `PlanProposal` 须经 compile + validation；禁止热改 active plan |
| **I-HPC-11** | 信任默认拒绝 | untrusted origin 默认 disabled |
| **I-HPC-12** | 与 C1/C5/C7/C8/C11 一致 | 不新增第七 phase；Capability 三维单调；事件闭集 |

---

## 10. 分阶段实施计划

> 完整 PR 清单：[0199-implementation-plan.md](../specs/0199-implementation-plan.md)（52 PR / 3 Lane / Agent Brief）。

```text
Phase 0 — 冻结事实边界（本 ADR）                    [Done]
  ├─ ADR-0199 Accepted/Proposed + 索引
  ├─ 不变量 I-HPC-* + SSOT 扩展表
  └─ 现有 CI 继续通过（plugin shape, kernel boundary, event catalog, phase graph）

Phase 1 — Runtime Facade + RunIntent（已批准）     [In Progress]
  ├─ lca/contracts/runtime/intent.py — RunIntent, SessionActivation, RuntimeFacade Protocol
  ├─ lca/application/runtime/facade.py — adapter 包装 run_kernel + RunCoordinator
  ├─ transport RunRequest → RunIntent adapter（不改 RunPort 签名）
  ├─ lca-ops runs create 经 facade（与 HTTP 同路径）
  └─ 验收：同一 RunIntent @ CLI/HTTP/test → 相同 plan_ref；入口零 direct provider/journal

Phase 2 — Plugin Doctor
  ├─ lca/harness/diagnostics/doctor/ — profile + plugin dry-run
  ├─ DoctorReport JSON schema + stable codes
  ├─ lca-ops doctor profile|plugin [--ci]
  └─ 验收：未 setup 即可发现 duplicate id, missing dep, cardinality, undeclared privilege, expired compat

Phase 3 — Capability / Privilege 分离
  ├─ PluginSpec / PluginContract 扩展 privileges + PluginOrigin
  ├─ EffectPolicyPlan 投影统一 effects/gates/safe_executor 语义
  ├─ 与 ADR-0197 Guard stack 同系列 PR
  └─ 验收：undeclared privilege → setup fail-loud；doctor 报告 DOC-PRIV-*

Phase 4 — 内容型扩展与自我改进
  ├─ ResourceRegistry + namespaced skill/role/prompt ID
  ├─ PlanProposal → compile → review → activate 闭环
  └─ 验收：skill 不可扫描注册 tool；PlanProposal 不可热改 active plan

Phase 5 — 外部插件隔离与生态
  ├─ untrusted → MCP / sandbox / worker
  ├─ plugin SDK + compat manifest + doctor CI + 最小示例 repo
  └─ 验收：trust=untrusted 默认 disabled；external 高风险 capability 不经进程内 fiber
```

**依赖顺序**：Phase 1/2 可在 P0 事实单轨（ADR-0194/0195 P1）达标后并行；Phase 3 依赖 Phase 2 doctor 报告面；Phase 4/5 依赖 Phase 3 权限模型。

---

## 11. CI / 架构门禁扩展

| ID | 断言 | 范围 |
|---|---|---|
| HPC-L1 | L0 handler 不 import cognition/runtime provider 实现 | transport-isolation 扩展 |
| HPC-L2 | 生产路径经 `RuntimeFacade` 或标注 COMPAT 豁免 | grep + arch test |
| HPC-L3 | 新插件禁止引用旧 `PluginManifest` 类型 | `route_legacy_patterns.py` |
| HPC-L4 | capability key 匹配 `domain.subject[.variant]` | `check_plugin_shape.py` 扩展 |
| HPC-L5 | doctor `--ci` 在 golden profiles 零 error | CI job |
| HPC-L6 | durable EP payload 含 `plan_ref` 或 `activation_ref` | event catalog test |
| HPC-L7 | untrusted origin 无 profile enable 时不得进入 ResolvedProfile | resolve test |
| HPC-L8 | 禁止新 global mutable tool registry | lint / import boundary |

**基线协议**：`lint-imports` 与 `check_package_contracts.py` 既有失败须区分 **本次引入 vs 既有**；仅 exit 0 可称通过。

---

## 12. 兼容与迁移

### 12.1 COMPAT 模板（新代码禁用旧路径）

```text
# COMPAT(owner: ADR-0199, from: transport-direct-boot, to: RuntimeFacade,
# delete_when: HPC-L2 grep 零非豁免命中, forbidden_new_usage: handler 内 resolve_profile)
```

### 12.2 关键迁移对照

| 旧入口 | 新入口 | 过渡期 |
|---|---|---|
| handler 内 `resolve_profile` | `RuntimeFacade.resolve_activation` | Phase 1 adapter；Phase 2 doctor 警告 |
| transport `RunRequest.ctx` 作 boot 来源 | K3 booted ctx via activation | Phase 1 保留 ctx 字段；deprecated |
| 散落 doctor scripts | `lca-ops doctor` | Phase 2 统一；旧脚本 COMPAT |
| `meta.relations:` YAML fallback | typed capability relations | Phase 3 警告；Phase 4 CI fail |
| `@plugin` alias keys | canonical `contract=` | ADR-0110 窗口；doctor 报告 |

### 12.3 Hermes 式 compat 政策（借鉴，非复制）

- 废弃行为：replacement + release notes + **一次/进程** warning + **至少两 minor** 支持窗口
- 到期后：CI fail-close；persisted data 须 migration 或 replay 说明
- 插件内部 import 路径 **不是** LCA 公共契约；但 `@plugin` 公共 API 遵循上述窗口

---

## 13. 验证

### 13.1 Phase 0（本 ADR）

```bash
uv run python scripts/verify_md_links.py
uv run python scripts/verify_doc_budgets.py
uv run pytest tests/scenario/refactor/test_refactor_guards.py::TestAdrIndexMatchesFilesystem -q
```

### 13.2 Phase 1 验收

```bash
# 同一 profile 跨入口 plan_ref 一致
uv run pytest tests/application/test_runtime_facade_plan_ref_parity.py -q
uv run pytest tests/architecture/test_0199_phase1_acceptance.py -q
./scripts/lca-ops profile inspect --json profiles/web-standard.yaml
```

### 13.3 Phase 2 验收

```bash
./scripts/lca-ops doctor profile profiles/web-standard.yaml --ci --json
uv run pytest tests/harness/diagnostics/test_plugin_doctor.py -q
```

### 13.4 全阶段回归（每次 Phase PR）

```bash
uv run ruff check && uv run ruff format --check
uv run pytest tests/golden/test_8_profiles.py -q
uv run pytest tests/architecture/test_0194_0195_acceptance.py -q
./scripts/lca-ops audit-plugin-shape
```

---

## 14. 明确不做的事

1. **不** 采用 Hermes 单一中心 tool registry 作为 LCA 插件总线
2. **不** 把所有认知能力压成 tool schema
3. **不** 允许插件绕过 `FactGateway` 写 journal
4. **不** 允许 skill 通过文本扫描自动获得执行权限
5. **不** 允许自我改进直接修改当前 active plan
6. **不** 为兼容旧路径无限期保留 shim（必须有 owner + delete-when + CI）
7. **不** 在 doctor 路径执行修复性副作用
8. **不** 新增第七 cognitive phase 或 Gate graph node（C1）

---

## 15. Alternatives considered

### 15.1 全面照搬 Hermes `AIAgent` + central registry

Hermes 已验证多入口与工具生态。但 LCA 插件异构性（phase/gate/transport/memory）使 central registry 丢失 compile-time 验证与认知语义；且 import-time register 破坏分层 import 法。**否决**。

### 15.2 仅文档收敛，不引入 RuntimeFacade

可继续靠 ADR-0195 三时态与现有 RunPort 维持。但 CLI/kernel/web 仍重复 resolve/boot；doctor 仍分散；无法达成 Hermes 级「一个 front door」。**否决**作为长期方案；允许 Phase 1 adapter 过渡。

### 15.3 Doctor 作为独立规则引擎（复制 Hermes 脚本）

实现快，但与 `compile_run_plan` validators 双轨，长期 drift。**否决**；Doctor 必须调用 compile pipeline dry-run。

### 15.4 废弃 PhaseGraph，统一为 Hermes conversation loop

简化 mental model，但丧失 Gate 子链、phase 级 replay、Guard tier 与 ADR-0194/0197 已落地投资。**否决**。

### 15.5 全插件进程外（MCP/worker only）

安全最优，但 latency 与 trusted core 插件（phase executor、reducer）不匹配。**部分采纳**：仅 untrusted/external 强制隔离；trusted 继续 Cordis fiber。

---

## 16. 与其他 ADR 关系

| ADR | 0199 关系 |
|---|---|
| **0195** | 0195 定义三时态与五平面；0199 在 L1 入口与 L3 插件治理层落地 Hermes 工程能力 |
| **0194** | 0194 保六 phase + FactGateway；0199 不修改 loop 语义 |
| **0197** | privileges/effects 投影与 Guard stack 合并实施 |
| **0198** | Doctor 读 CompiledPlan；观测 compile graph 与 run compile graph 同构 |
| **0068/0075** | CompiledRunPlan / PhaseGraph 仍是 run SSOT；0199 增加 Activation 绑定 |
| **0115/0119** | Transport 仍 carrier；RunRequest 降为 L0 adapter |
| **0187** | Assistant 绑定经 RunIntent.assistant_id；不新开平行入口 |
| **0200** | 0199 管「怎么跑」；0200 管「助理学什么/怎么定时/怎么策展」— 见 §16.1 |

**0195 是平台壳；0199 是入口与插件治理壳。** 实施时 0199 Phase 1–2 与 0195 P3（Transport 瘦身）可协同，但 0199 不阻塞 0194/0195 事实单轨 P1。

### 16.1 与 ADR-0200 的分工（禁止合并为一篇）

| 维度 | ADR-0199（平台机制） | ADR-0200（产品能力） |
|---|---|---|
| 问题 | 入口如何统一、插件如何治理、plan 如何绑定 | 个人助理如何学习、策展、压缩、定时 |
| 锚点 ADR | 0194/0195/0068/0115 | 0187/0067/0093/0048/0169 |
| 核心产物 | `RunIntent`、`RuntimeFacade`、`DoctorReport`、`PluginOrigin` | review-fork、Curator、ContextEngine 槽、MemoryProvider、no_agent Routine |
| 可启动时机 | Phase 1 已批准（不依赖 0187 PR-2） | 须服从 0187 P0→P1→P2 产品顺序 |
| Hermes 吸收面 | facade、manifest、doctor、trust、registry 纪律 | 产品闭环五件事（§0200 §1.2） |

**合并否决理由**：验收标准、实施阶段、依赖链、owner seam 均正交；合并会再造一篇 0195 级 mega ADR，且让平台 Phase 1 被产品 PR 阻塞。

---

## 17. 验收（0199 Done）

1. 新人读 ADR-0199 + [runtime-entry-walkthrough](../specs/runtime-entry-walkthrough.md) + SSOT 扩展表，30 分钟内能说明从任意 surface 到 `plan_ref` 的单一路径。
2. CLI、HTTP、测试三入口对同一 `RunIntent` 产出相同 `plan_ref`（Phase 1）。
3. `lca-ops doctor profile --ci` 在 8 golden profiles 零 error（Phase 2）。
4. 新插件零 undeclared privilege；untrusted 默认 disabled（Phase 3）。
5. skill/resource 零隐式 tool 注册（Phase 4）。
6. Doctor、replay、failure attribution 可通过 `activation_ref` 定位闭包（Phase 2+）。
7. HPC-L1–L8 门禁建立且区分既有 baseline 失败。

---

## 18. 参考

- [Hermes Agent Architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture) — 多入口 `AIAgent`、registry、gateway、plugin 子系统
- [Hermes Plugin Guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins) — manifest、doctor、capabilities、trust、portable plugins v1
- 本地 Hermes 安装（对标阅读）：`~/.hermes/hermes-agent/`（`hermes_cli/plugins.py`、`hermes_cli/plugin_dev.py`、`run_agent.py`、`tools/registry.py`）
- [Runtime Entry Walkthrough](../specs/runtime-entry-walkthrough.md) — 现有 L0–L7 入口链
- [Platform Directory Architecture](../specs/platform-directory-architecture.md)
- [0194-0195 Implementation Plan](../specs/0194-0195-implementation-plan.md)
- [Declarative Phase Graph Spec](../specs/declarative-phase-graph-spec.md)
- [Plan Compile and Execute Walkthrough](../specs/plan-compile-and-execute-walkthrough.md)
