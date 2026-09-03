# ADR-0180 — 事件机制：kernel 元层插件 + 鉴权矩阵 SSOT

## 状态

Accepted（试点实现同期提交；通过即锁）。

## 背景

LCA 现行事件层是把"一组 helper 类的合集"做成 plugin 形态：

- `lca/plugins/observability/spine/reflectors/{cognition,body_llm,runtime,agent_spawn}.py` —— 4 个 reflector 文件承载 ~40 个 `emit_xxx` 函数
- `lca/cognition/body/tool_journal_emit.py`、`lca/infrastructure/observability/spine/{transport_emit,exception_emit,emit_pipeline}.py` —— 5 个 helper
- `lca/runtime/envelope_emitter.py` —— `_safe_emit` 间接层
- `lca/contracts/models/observability/journal.py` —— 49 个 `JournalEvent` 子类（frozen dataclass）
- `lca/contracts/models/observability/journal_catalog.py` + `lca/infrastructure/observability/events/event_descriptors_data.py` —— 两份等价注册表
- `lca/contracts/observability/cordis_event_table.py` —— `EventDescriptor.derive()` 字符串 glob

由此引发 4 个真问题：

1. **机制被当 feature 做**：sender / consumer / router 都是普通 `@plugin`，业务 plugin 与机制 plugin 在同一注册表里——机制可被业务 plugin 替换，破坏不变量。
2. **没有鉴权**：任何 plugin 都能 import 任何 `JournalEvent` 子类并 `record()`；任何 consumer 都能订阅任何 category——"消费者偷听不属于他的事件"在物理上可行。
3. **裸字符串多**：`emitter="lca.x.y"` 字符串路径、`cordis_name="agent.*"` glob、`type_name=cls.__name__` 字面量——三处字符串各自独立。
4. **构造权与发送权不分离**：业务方 `record(DelegationCacheHit(...))` 既构造又触发，"发送者 SSOT" 是字面口号。

ADR-0179（已撤回）曾尝试在 `lca/plugins/events/` 下做 sender / consumer plugin，但方向错了——**机制本身不是 feature plugin**，它是 kernel 的一部分。

## 目标

事件机制是 **kernel 元层插件**：固定、不可替换；负责"哪些 plugin 可以 send 哪些事件 / 哪些 plugin 可以 subscribe 哪些事件"；公开面只有 `send()` 与 `subscribe()`；鉴权矩阵是 SSOT（yaml 目录）。

```text
┌────────────────────────────────────────────────────────────────────┐
│ lca_kernel/events   ← kernel 元层，固定，不可被 plugin 替换          │
│                                                                    │
│   EventMechanism  （meta-plugin）                                   │
│   ├─ EventRegistry  ← 加载 lca_kernel/events/config/**/*.yaml      │
│   │     鉴权矩阵：{category → publishers, subscribers,              │
│   │                              default_subscribers, payload_cls} │
│   ├─ Sender        ← 唯一 send 入口，鉴权 publishers 白名单         │
│   ├─ Router        ← 按 category fanout，鉴权 subscribers 白名单    │
│   └─ Sinks         ← 内置 sink：journal_sink（默认）/ 可选扩展     │
│                                                                    │
│   公开面：                                                          │
│     send(payload, *, plugin_id)                                     │
│     subscribe(plugin_id, category, callback)                        │
│   其他全部 internal                                                 │
└────────────────────────────────────────────────────────────────────┘
              ▲                                ▲
              │ 调 send（被授权时）            │ 调 subscribe（被授权时）
              │                                │
   ┌──────────┴─────────────┐       ┌──────────┴──────────┐
   │ 业务 plugins           │       │ 消费者 plugins       │
   │ - dispatch             │       │ - journal_sink      │
   │ - safe_executor        │       │ - cursor_consumer   │
   │ - team_mode            │       │ - console_projector │
   │ - llm_adapter          │       │ - runtime_tracer    │
   │ - ...                  │       │ - ...               │
   │                        │       │                      │
   │ 每个 plugin 在          │       │ 每个 plugin 在       │
   │ PluginSpec 声明        │       │ PluginSpec 声明     │
   │ event_publishes=       │       │ event_subscribes=  │
   │ (... categories)       │       │ (... categories)    │
   └────────────────────────┘       └──────────────────────┘
```

## 关键决策（5 条）

### D1. 机制 + 一切业务方都是 `@plugin`，按 pub/sub 统一目录

- **机制本体** (`lca_kernel/events/manifest.py`)：kernel 元层，`@plugin(id="lca.events.mechanism", ...)`，**唯一**。
- **统一目录** `lca/plugins/events/`，按 pub/sub 区分：
  - `publishers/<name>/` —— 业务方 producer plugin（如 `delegation_cache`），用 `@plugin` Manifest
  - `sinks/<name>/` —— sink plugin（如 `journal`），用 `@plugin` Manifest
  - `subscribers/<name>/` —— 业务方 consumer plugin（如 `console_projector`），用 `@plugin` Manifest
- **一切都是插件**：业务方调 `EventMechanism.send(payload, plugin=MyPluginClass)`；sink / subscriber 在自己 boot 时调 `EventMechanism.subscribe(plugin=MySinkClass, ...)`，机制按 yaml SSOT 鉴权。
- 业务 plugin 不能提供 `EventMechanism` 的替代实现；不能绕过机制直接发事件。
- profile 装载顺序：mechanism → sinks → subscribers → publishers（保证 boot 时机制已就绪）。

### D2. 鉴权矩阵是 SSOT（yaml 目录）

事件配置目录（SSOT）：

```
lca_kernel/events/config/
├── business/                ← 层次 = business
│   ├── team.yaml           ← 维度 = team
│   ├── tool.yaml           ← 维度 = tool
│   ├── llm.yaml            ← 维度 = llm
│   ├── gate.yaml           ← 维度 = gate
│   └── memory.yaml
├── observability/           ← 层次 = observability
│   ├── log.yaml            ← 维度 = log
│   ├── trace.yaml          ← 维度 = trace
│   └── metric.yaml
├── control/                 ← 层次 = control
│   ├── approval.yaml
│   ├── pause.yaml
│   └── policy.yaml
└── boot.yaml                ← 启动期特殊层次
```

每 yaml 文件（**字段值是 typed Python 实体全路径**，避免出错）：

```yaml
events:
  - category: team.delegation.cache_hit
    plane: lca.contracts.event.Plane.STRUCTURAL   # enum 全路径
    payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit  # class 全路径
    fields:
      callee_role: str
      subtask: str
      step: int
    publishers:                       # plugin id 字符串（与业务方 send(..., plugin_id=...) 对齐）
      - delegation_cache
    subscribers:                      # plugin id 字符串
      - journal_sink
      - cursor_consumer
      - console_projector
    default_subscribers:              # 机制 boot 时自动 subscribe（plugin 不必自调）
      - journal_sink
      - console_projector
```

字段值类型规范（**强约束，避免出错**）：

| 字段 | 类型 | yaml 形态 | 校验 |
|---|---|---|---|
| `category` | enum 值字符串 | `team.delegation.cache_hit` | 必须在 `contracts.event.Category` 闭集 |
| `plane` | enum 全路径 | `lca.contracts.event.Plane.STRUCTURAL` | 必须能 import 到 `Plane` 枚举成员 |
| `payload_class` | class 全路径 | `lca_kernel.events.payloads.TeamDelegationCacheHit` | 必须能 import 且 `issubclass(EventPayload)` |
| `publishers` / `subscribers` / `default_subscribers` | plugin id 字符串 | `delegation_cache` 等 | 不解析（运行时机制按 id 鉴权） |

→ 任何字段解析失败 → `UnknownCategoryError`，机制 fail-fast。

### D3. PluginSpec 自我声明 + 机制校验

`PluginSpec`（`lca/contracts/protocols/declarative/declarative_plugin.py`）新增两个字段：

```python
event_publishes: tuple[Category, ...] = ()   # 该 plugin 声明要 publish 哪些 category
event_subscribes: tuple[Category, ...] = () # 该 plugin 声明要 subscribe 哪些 category
```

机制在 boot 时校验：

- `event_publishes ⊆ EventRegistry.publishers[category]`（每个声明的 category 都要在 SSOT 的 publishers 白名单里）
- `event_subscribes ⊆ EventRegistry.subscribers[category]`
- 不允许"声明发 X 但 yaml 没列"；也不允许"yaml 列为 X 的 publisher 但 plugin 没声明"

→ manifest 是 self-declaring + 与 SSOT 互校验，防"插件偷发 / 偷听"。

### D4. 公开面只有 send / subscribe

- 业务 plugin **只**调 `EventMechanism.send(payload, *, plugin_id)` 与 `EventMechanism.subscribe(plugin_id, category, callback)`
- **不** import `Event` 类、`EventRef`、`Router`、`ConsumerRegistry`、`JournalSink` 等内部组件
- **不** 直接调 `BoundObservability.journal.write()`——journal sink 由机制自己管

→ 物理上无法绕开鉴权；"消费者偷听"在协议层就不可能。

### D5. 完全断开旧 `JournalEvent` 49 子类

- 旧 `lca/contracts/models/observability/journal.py` 49 子类**全部退役**
- 旧 `record(JournalEvent(...))` 不再被任何业务路径调用
- 旧 reflector（4 文件 40 函数）整体删除
- 旧 `event_descriptors_data.py` / `cordis_event_table.py` / `journal_catalog.py` 整体删除
- **不**提供 `LegacyJournalBridgeSink` 逃生口——D1 一致性优先于过渡期便利

旧 path 退役后，所有事件统一走 `EventMechanism.send()` → `JournalSink` 写盘 → `console_projector` / `cursor_consumer` / `runtime_tracer` 等消费者各自订阅。

## 49 事件 → 层次 × 维度 归位表

| 层次 | 维度（yaml） | category | publishers | subscribers |
|---|---|---|---|---|
| business | team | `team.casting.{started,completed,failed}` | team_mode | journal, console, cursor |
| business | team | `team.delegation.{issued,completed,cache_hit}` | delegation_cache, invocation | journal, console, cursor, reducer |
| business | team | `team.message.published` | team_handle | journal, console |
| business | tool | `tool.{started,invoked,denied,lifecycle_ended,abandoned_before_invoke,retry_progress}` | safe_executor, pipeline_safe_executor, phase_execution_policy | journal, console, reducer, cursor |
| business | llm | `llm.{call_started,call_completed,stream_token,stream_stall,tool_call_resolved}` | llm_adapter (adapters) | journal, console, tracer, reducer |
| business | gate | `gate.{decided,made,step_completed,action_degraded}` | decision_gates, body | journal, console, reducer |
| business | memory | `memory.{committed,compacted}` | simple_memory | journal, console |
| business | perception | `perception.{context_manifested,merged,step_text_delta,reasoning_delta,reasoning_completed,run_activity}` | perceive_hub, context_manifest, llm_adapter | journal, console, model_visible |
| observability | log | `runtime.observed` | "*"（任何 plugin） | journal, langfuse, console |
| observability | log | `exception.{caught,finally,lifecycle_finally}` | runtime exception handler | journal, exception_sink, console |
| observability | trace | `sandbox.output_delta` | sandbox | sse_projection, console |
| control | approval | `control.approval.{requested,resolved}` | safe_executor | approval_ui, journal |
| control | pause | `control.{run_paused,run_resumed,inbox_followup}` | runtime_loop, loop_drivers | journal, console, approval_ui |
| control | policy | `plugin.{authored,mounted,mount_rejected,unmounted,inspected}` | cordis_control | journal, console |
| control | policy | `preset.published` | preset_authoring | journal, console |
| boot | — | `boot.{profile_resolved,plugin_fiber_spawned,observability_assembled}` | lca_kernel | boot_logger |

**单 yaml 唯一归属**：跨层次共享 category 不允许（如 `tool_call_resolved` 归 `business/llm`）；如未来真有 dual-nature，再走 RFC。

## 试点范围（P2，与 ADR-0179 同一边界）

| 项 | 范围 |
|---|---|
| 机制实现 | `lca_kernel/events/` 完整 4 文件（mechanism / registry / auth / sinks/journal）+ 1 个 yaml |
| 配置 SSOT | `lca_kernel/events/config/business/team.yaml`（1 个事件：`team.delegation.cache_hit`） |
| 业务方迁 | `lca/cognition/body/delegation_cache.py` —— 改为 `EventMechanism.send(TeamDelegationCacheHit(...), plugin_id="delegation_cache")` |
| 测试 | 5 套：`test_mechanism_auth` / `test_registry_load` / `test_sinks_journal` / `test_consumer_subscribe` / `test_pilot_delegation_cache` |
| **不在范围** | 其他 48 事件、其他 29 个 A 类业务模块、reducer / cursor / boot、tool / llm / approval、旧 49 子类删除（按 §迁移 PR 切分后续推进） |

## 迁移 PR 切分（试点通过后启动）

每 PR 一个 yaml + 一个业务模块 + 配套测试；删-when 见每 PR 头：

| PR | 范围 | 删-when |
|---|---|---|
| 试点 PR（本 ADR） | 机制 + 1 个 yaml + delegation_cache | — |
| 2 | `business/team.yaml` 补齐（casting, delegation_issued, delegation_completed, team_message） | 4 yaml 行 + team_mode 迁完 |
| 3 | `business/tool.yaml` + safe_executor 迁 | safe_executor 旧路径 `rg = 0` |
| 4 | `business/llm.yaml` + adapters 迁 | 旧 LLM reflector 删 |
| 5 | `business/gate.yaml` + decision_gates 迁 | — |
| 6 | `business/memory.yaml` + simple_memory 迁 | — |
| 7 | `business/perception.yaml` + perceive_hub 迁 | — |
| 8 | `observability/log.yaml` + runtime observed + exception | 旧 exception_emit 删 |
| 9 | `observability/trace.yaml` | 旧 stream reflector 删 |
| 10 | `control/approval.yaml` + safe_executor (control 部分) | — |
| 11 | `control/pause.yaml` + runtime_loop | 旧 runtime_emitter 删 |
| 12 | `control/policy.yaml` + cordis_control + preset_authoring | 旧 plugin_emit 删 |
| 13 | `boot.yaml` | lca_kernel 三件套 emit 路径删 |
| 14 | reducer 改造为 consumer | reducer 不再写 state；改 consumer 订阅 `gate.*` / `action.*` |
| 15 | cursor 改造为 consumer | `coord.emit_phase` / `CoordinatorAdapter.emit_phase` 删除 |
| 16 | 旧 reflector 4 文件整体删除 | `rg "from .reflectors" lca/ = 0` |
| 17 | 旧 `journal.py` 49 子类 + `journal_catalog.py` 删除 | `rg "JournalEvent" lca/ = 0` |
| 18 | `event_descriptors_data.py` / `cordis_event_table.py` 删除 | `rg = 0` |
| 19 | 旧 `record()` facade 删除 | `rg = 0` |

## 取代与吸收

| 被取代/吸收 | 条款 |
|---|---|
| ADR-0179 | **Superseded**——方向错误（机制当 plugin 做） |
| ADR-0063 PR-7 | **Superseded**——descriptor 注册表改为 yaml SSOT |
| ADR-0116 boot 事件 | **Superseded**——boot 事件走 `lca_kernel/events/config/boot.yaml` |
| ADR-0168-final §D14 | **Superseded**——`cordis_name` 由 SSOT 推导，无字符串 glob |
| ADR-0169 §11 cursor 适配 | **Superseded**——`coord.emit_phase` 删，cursor 是 consumer |
| `exception-caught-single-emitter.md` | **吸收**——单 emitter 原则作为机制 D5 的子集 |

## 试点"盖章"判定

试点 PR 合并前必须回答 4 个问题：

1. **业务方 ≤ 1 行 + typed payload + 鉴权声明**：业务方能否只调一行 `EventMechanism.send(TeamDelegationCacheHit(...), plugin_id="...")`？
2. **鉴权白名单按设计工作**：未在 yaml `publishers` 白名单的 plugin 调 `send()` → raise `UnauthorizedPublish`；未在 `subscribers` 白名单的 plugin 调 `subscribe()` → raise `UnauthorizedSubscribe`。
3. **消费者偷听防护**：plugin A 订阅 `team.delegation`，机制按 yaml 路由；plugin B 试图 `subscribe("tool.*", ...)` 但 yaml 未授权 → raise。
4. **plugin manifest 与 yaml SSOT 互校验**：plugin manifest `event_publishes=["team.delegation.cache_hit"]` 但 yaml 未列该 plugin → boot 失败。

4 个问题都通过 → 试点锁定，进入 PR 2–19 灰度。

## 风险与回滚

- **风险 1**：业务 plugin 大量需要重写（30+ 个 A 类模块）。**缓解**：试点只 1 个；后续 PR 每个 PR 一个 yaml + 一个模块，灰度推进。
- **风险 2**：journal sink 写入新格式，旧 journal reader 不识别。**缓解**：新机制接管 journal 写盘后，旧 reader 改读新格式；过渡期由 profile 决定是否开启旧 reader。
- **风险 3**：机制不能被 plugin 替换 → 长期可维护性受限于 kernel 升级节奏。**缓解**：机制本身通过"事件配置 SSOT"扩展（新增 yaml 文件即可新增事件），不需要改机制实现。
- **回滚**：试点 PR 不删任何旧路径，回滚 = 撤回试点 PR 即可。
