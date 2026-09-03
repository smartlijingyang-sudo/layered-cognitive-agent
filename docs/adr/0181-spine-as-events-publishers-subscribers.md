# ADR-0181 — Spine 全部走 ADR-0180 EventMechanism：spine 自身不持机制

## 状态

Accepted（试点实现同期提交；通过即锁）。

## 背景

LCA 现行 spine 是独立机制本体：

- `lca/infrastructure/observability/spine/event_spine.py` — `EventSpine.append()` 单入口,做 hash chain、sequence、epoch、fanout 到 sinks + subscribers
- `lca/infrastructure/observability/spine/event_record.py` — `EventRecord` frozen dataclass;`execution_point` 76 个字符串白名单(`EXECUTION_POINTS`)、hash chain、`FD-1 sink fail-fast` / `FD-2 subscriber contained`
- `lca/infrastructure/observability/spine/manifest.py` — 76 EP 字符串闭集,`EventRecord.__post_init__` 强校验
- `lca/plugins/observability/spine/reflectors/{cognition,body_llm,runtime,agent_spawn,transport,context,signature,source}.py` — 8 个 reflector,40+ 个 `emit_xxx()` 函数
- `lca/infrastructure/observability/spine/sinks/{file_sink,routing_file_sink,tracing_file_sink,otel_trace,...}.py` — 4+ 个 sink
- `lca/infrastructure/observability/spine/derivers/{step_tree_accumulator,graph,waterfall,narrative,live_tail,...}.py` — 8 个 deriver

ADR-0180 已把"事件机制"做成 kernel 元层 plugin(`lca_kernel/events/EventMechanism`),但 spine 仍是独立机制。两条总线并存引发 4 个真问题：

1. **机制不唯一**：`EventMechanism` 与 `EventSpine` 都是单入口，业务方混用；机制的可替换面扩大，违反"一切走 180"原则。
2. **机制与业务方同目录**：`lca/infrastructure/observability/spine/` 装机制 + sink + deriver，业务方 reflector 在 `lca/plugins/observability/spine/reflectors/`，机制可被业务 plugin 替换风险仍在。
3. **0 鉴权**：`EventSpine.subscribe(fn)` 谁都能调；reflector 之外的业务 plugin 偷听 `cognition.*` EP 无任何阻拦（spine 76 EP 跨 5 层，比 ADR-0180 试点 1 个 `team.delegation.cache_hit` 严重得多）。
4. **构造权与发送权不分离**：业务方 `spine.append(execution_point=..., channel=..., payload=...)` 既构造 `EventRecord` 又触发，发送者 SSOT 是字面口号。

## 目标

**spine 自身不持机制**。`lca_kernel/events/EventMechanism`（ADR-0180）是 LCA 唯一事件机制；spine 全部降级为挂载在 EventMechanism 上的 publishers / sinks / subscribers。`lca/infrastructure/observability/spine/event_spine.py` 整体退役。

```text
┌────────────────────────────────────────────────────────────────────┐
│ lca_kernel/events   ← 唯一机制（ADR-0180 D1），固定                  │
│                                                                    │
│   EventMechanism  （meta-plugin）                                  │
│   ├─ EventRegistry  ← 加载 lca_kernel/events/config/**/*.yaml      │
│   │     鉴权矩阵：{category → publishers, subscribers,             │
│   │                              default_subscribers, payload_cls} │
│   ├─ Sender        ← 唯一 send 入口，鉴权 publishers 白名单         │
│   ├─ Router        ← 按 category fanout，鉴权 subscribers 白名单    │
│   └─ Sinks         ← 内置 sink：journal_sink（默认）/ 可选扩展     │
│                                                                    │
│   公开面：                                                          │
│     send(payload, *, plugin=MyClass)                               │
│     subscribe(plugin=MyClass, category, callback)                  │
└────────────────────────────────────────────────────────────────────┘
              ▲                                ▲
              │  调 send（被授权时）           │  调 subscribe（被授权时）
              │                                │
   ┌──────────┴───────────────────────────────┴────────────┐
   │  spine 全降级为 publishers / sinks / subscribers       │
   │                                                        │
   │  lca/plugins/events/publishers/spine_*  （旧 reflector）│
   │  lca/plugins/events/sinks/spine_*       （旧 sink）    │
   │  lca/plugins/events/subscribers/spine_* （旧 deriver） │
   │                                                        │
   │  每个 plugin 在 PluginSpec 声明                          │
   │  event_publishes= / event_subscribes=                   │
   └────────────────────────────────────────────────────────┘
```

spine 自身的 4 个 LCA 特性（EP 白名单 / hash chain / FD-1 / FD-2）的归宿：

| spine 特性 | 新位置 | 备注 |
|---|---|---|
| EP 白名单（76 字符串） | `lca_kernel/events/config/observability/spine.yaml` 76 行 | ADR-0180 D2 yaml 闭集；不引 enum（EP 跨 5 层） |
| hash chain + sequence + epoch + span | `SpineEventPayload` 壳类自带字段；`spine_chain_sink` 在落盘前算 chain | ADR-0180 机制不感知 chain；spine sink 自己做 |
| FD-1 sink fail-fast | **升级为 `EventMechanism` 通用失败语义**（ADR-0180 补 D6） | 试点 PR 改 `lca_kernel/events/mechanism.py` |
| FD-2 subscriber contained | **升级为 `EventMechanism` 通用失败语义**（ADR-0180 补 D6） | 同上 |

## 关键决策（5 条）

### D1. 机制唯一：spine 不持机制，EventMechanism 是 LCA 唯一事件入口

- `lca/infrastructure/observability/spine/event_spine.py` **整体退役**。
- 业务方只调 `EventMechanism.send(payload, *, plugin=MyPluginClass)`，其中 `payload` 是 `SpineEventPayload`（壳类，承载 `execution_point` + `payload` dict）。
- `lca_kernel/spine/` **不建**（不复刻 ADR-0180 范式到一个平行机制）。
- 旧 `EventRecord` frozen dataclass 退役；`SpineEventPayload` 是其替代（见 D2）。
- profile boot 顺序：mechanism（kernel 元层）→ sinks（journal_sink + spine_chain_sink）→ subscribers（deriver 集合）→ publishers（reflector 集合）。

### D2. SpineEventPayload：1 个壳类承载 EP + payload，套进 EventMechanism

spine 当前 `EventRecord` 是 1 个 frozen dataclass，76 个 EP 用字符串白名单。复用 ADR-0180 范式最干净的形态：**1 个壳类** + 76 个 category 在 yaml 闭集：

```python
# lca_kernel/events/payloads/spine.py
class SpineEventPayload(EventPayload):
    """壳类：承载 spine EP + payload dict + chain 字段。"""
    execution_point: str       # 原 EXECUTION_POINTS 字符串
    channel: str               # fact/control/error/diagnostic
    payload: dict[str, Any]    # 原 caller_payload
    span_id: str | None        # 由 SpiineContext 注入
    parent_span_id: str | None
    sequence: int              # 机制层注入
    epoch: int
    prev_event_hash: str | None
```

- `execution_point` 字段替代原 `EventRecord.execution_point` 字符串；`SpineEventPayload.__post_init__` 校验 `execution_point ∈ SPINE_EXECUTION_POINTS`（76 个闭集，单独常量；不是 enum，跨层不能用 enum）。
- `EventMechanism.send(SpineEventPayload(...), plugin=...)` 不动；机制只认 `payload.category` 做鉴权，**不**感知 spine 内部字段。
- hash chain 由 `spine_chain_sink` 落盘前算（`prev_event_hash` 在 sink 内做 sha256），不进 `EventMechanism` 主路径。

### D3. 鉴权矩阵 = spine.yaml 76 行 closure，PluginSpec 互校验

`lca_kernel/events/config/observability/spine.yaml`（层次 = observability，与 ADR-0180 团队/工具/感知 yaml 平级）：

```yaml
events:
  - category: spine.cognition.brain.perceive.start
    payload_class: lca_kernel.events.payloads.spine.SpineEventPayload
    publishers:
      - spine_reflector_cognition
    subscribers:
      - spine_file_sink
      - spine_step_tree_accumulator
      - spine_console_projector
    default_subscribers:
      - spine_file_sink

  - category: spine.cognition.brain.perceive.end
    ...

  # ... 76 行（试点 PR 只 1 行）
```

- 字段值类型同 ADR-0180 D2：`category` 字符串、payload_class 全路径、publishers/subscribers plugin id。
- 试点 PR 只 1 个 category（`spine.cognition.brain.perceive.start`）+ 1 publisher + 1 sink + 1 subscriber；其余 75 行 + 业务方按 §迁移 PR 切分后续推进。
- `PluginSpec.event_publishes / event_subscribes`（ADR-0180 D3）校验：plugin 声明的 category ⊆ yaml 白名单；yaml 列为 X 的 plugin 但 plugin 未声明 → boot 失败。

### D4. 公开面只有 send / subscribe；FD-1 / FD-2 升级为 EventMechanism 通用语义

- 业务方（含旧 reflector）**只**调 `EventMechanism.send(SpineEventPayload(...), plugin=MyPluginClass)` 与 `EventMechanism.subscribe(plugin=MyClass, category, callback)`。
- **不** import `EventSpine` / `EventRecord` / `SpineContext`（除 `SpineContext` 仍保留为 spine 内部 context，给 `spine_chain_sink` 算 hash chain 用；`SpineContext` 不下沉到业务方）。
- **不** 直接调 `BoundObservability.journal.write()`（journal sink 由机制自己管）。
- **FD-1 / FD-2 升级为 EventMechanism 通用失败语义**（ADR-0180 补 D6，试点 PR 同 PR 改 `lca_kernel/events/mechanism.py`）：
  - FD-1：sink 抛错 → fail-fast 传给 sender。
  - FD-2：subscriber 抛错 → contained，记 `event_mechanism.subscriber_failed` 内部事件，原事件仍落盘。
- → 物理上无法绕开鉴权；"消费者偷听"在协议层就不可能。

### D5. 完全断开旧 EventSpine / 76 EP 反射

- 旧 `lca/infrastructure/observability/spine/{event_spine,event_record}.py` **整体退役**。
- 旧 `lca/infrastructure/observability/spine/manifest.py`（76 EP 字符串闭集）**整体退役**；EP 闭集迁到 `lca_kernel/events/payloads/spine.SPINE_EXECUTION_POINTS`（常量，单独文件）。
- 旧 `lca/plugins/observability/spine/reflectors/` 8 个 reflector 文件 40+ `emit_xxx()` 整体迁到 `lca/plugins/events/publishers/spine_*/`。
- 旧 `lca/infrastructure/observability/spine/sinks/` 4+ 个 sink 整体迁到 `lca/plugins/events/sinks/spine_*/`。
- 旧 `lca/infrastructure/observability/spine/derivers/` 8 个 deriver 整体迁到 `lca/plugins/events/subscribers/spine_*/`。
- 旧 `set_active_spine` / `get_active_spine` / `safe_append`（`lca/plugins/observability/spine/_spine_safety.py`）退役；`SpineContext` 仅保留给 `spine_chain_sink` 内部用。
- **不**提供 `LegacySpineBridgeSink` 逃生口（D1 一致性优先于过渡期便利）。

## 试点范围（P1，与 ADR-0180 P2 试点同一边界）

| 项 | 范围 |
|---|---|
| 机制补 D6 | `lca_kernel/events/mechanism.py` 加 FD-1 / FD-2 通用失败语义 |
| SpineEventPayload 壳类 | `lca_kernel/events/payloads/spine.py`（1 个 class + 76 EP 闭集常量） |
| 配置 SSOT | `lca_kernel/events/config/observability/spine.yaml`（**只 1 个事件**：`spine.cognition.brain.perceive.start`） |
| 业务方迁 1 | `lca/plugins/events/publishers/spine_reflector_cognition/`：1 个 `emit_brain_perceive_start` 函数迁到 `EventMechanism.send(SpineEventPayload(...), plugin=RefClass)` |
| sink 迁 1 | `lca/plugins/events/sinks/spine_chain_sink/`：1 个新 sink，承担 hash chain 落盘（替代旧 `file_sink` 的 chain 部分） |
| subscriber 迁 1 | `lca/plugins/events/subscribers/spine_step_tree_accumulator/`：1 个 deriver 迁到 `EventMechanism.subscribe(...)` |
| 测试 | 4 套：`test_spine_payload_validate` / `test_spine_yaml_load` / `test_spine_publisher_auth` / `test_spine_chain_sink_e2e` |
| **不在范围** | 其余 75 EP、其他 7 reflector、其他 3+ sink、其他 7 deriver、cursor / reducer / projection_host 耦合点（按 §迁移 PR 切分后续推进） |

## 迁移 PR 切分（试点通过后启动）

每 PR 一个 yaml 扩行 + 一个 reflector 迁 + 配套测试；删-when 见每 PR 头：

| PR | 范围 | 删-when |
|---|---|---|
| 试点 PR（本 ADR） | 机制 D6 + SpineEventPayload + 1 yaml 行 + 1 publisher + 1 sink + 1 subscriber | — |
| 2 | `spine.yaml` 补 cognition 余 13 EP + cognition reflector 余 13 emit | `rg "emit_brain_" lca/plugins/observability/spine/ = 0` |
| 3 | `spine.yaml` 补 body_llm EP + body_llm reflector | 旧 body_llm reflector 删 |
| 4 | `spine.yaml` 补 runtime EP + runtime reflector + ADR-0169 cursor 改造为 subscriber | `coord.emit_phase` 删（与 ADR-0180 PR-15 同步） |
| 5 | `spine.yaml` 补 agent_spawn EP + agent_spawn reflector | 旧 agent_spawn reflector 删 |
| 6 | `spine.yaml` 补 transport/context/signature/source reflector EP | 旧 transport/context/signature/source reflector 删 |
| 7 | spine sinks 全迁（file_sink / routing_file_sink / tracing_file_sink / otel_trace） | `rg "from lca.infrastructure.observability.spine.sinks" lca/ = 0` |
| 8 | spine derivers 全迁（step_tree_accumulator / graph / waterfall / narrative / live_tail） | `rg "from lca.infrastructure.observability.spine.derivers" lca/ = 0` |
| 9 | 旧 `event_spine.py` / `event_record.py` / `manifest.py` 删除 | `rg "EventSpine\b" lca/ = 0` |
| 10 | 旧 `_spine_safety.py` 删除（`safe_append` / `set_active_spine` / `get_active_spine` 退役） | `rg "safe_append\|set_active_spine" lca/ = 0` |
| 11 | writable_matrix 改造：`writable_matrix.append` 调 `EventMechanism.send(..., plugin=WritableMatrixPlugin)` | 旧 path `rg = 0` |
| 12 | ProjectionHost（ADR-0170）改走 `EventMechanism.subscribe` | 旧 `host.drive` 路径废 |
| 13 | reducer 改造为 subscriber | reducer 不再写 state；改 subscribe `gate.*` |

## 取代与吸收

| 被取代/吸收 | 条款 |
|---|---|
| ADR-0165（spine EP 白名单） | **Superseded** — EP 闭集迁 `lca_kernel/events/payloads/spine.SPINE_EXECUTION_POINTS`；yaml closure 替代 |
| ADR-0165.1（spine schema / FD-1 / FD-2） | **部分 Superseded** — FD-1/FD-2 升级为 EventMechanism 通用语义（D4 + 机制 D6）；hash chain 仍 spine sink 自管 |
| ADR-0167（Coordinator.record_* 唯一写路径） | **Superseded** — coordinator 不再写 spine，改为 EventMechanism 业务方 publisher |
| ADR-0169（cursor 适配） | **Superseded** — `coord.emit_phase` 删，cursor 是 EventMechanism subscriber |
| ADR-0170（ProjectionHost） | **吸收** — host 直接订 EventMechanism.subscribe，spine 不再持有 subscriber 列表 |
| ADR-0175（spine 扩 EP payload） | **保留** — step_tree_accumulator 仍写 `model_visible/`，迁到 subscriber 后职责不变 |

## ADR-0180 补 D6（FD-1 / FD-2 通用失败语义，试点 PR 同 PR 改）

`EventMechanism`（ADR-0180）当前未明确 sink / subscriber 失败语义。0181 spine 试点要求机制具备 FD-1 / FD-2，补一条 D6 写入 ADR-0180（试点 PR 改 `lca_kernel/events/mechanism.py` 同 PR 落）：

```text
D6. 失败语义
  - FD-1（sink 失败 = fail-fast）：首个 sink 抛错 → 异常上抛 sender。
  - FD-2（subscriber 失败 = contained）：subscriber 抛错 → 记
    event_mechanism.subscriber_failed 内部事件，原事件仍落盘。
  - 适用范围：所有 events 业务方（含 0180 试点 delegation_cache）。
```

试点 PR 必须额外跑 `tests/plugins/events/publishers/test_delegation_cache.py` 确认 0180 业务方在 FD-1/FD-2 新语义下行为不变（regression lock）。

## 试点"盖章"判定

试点 PR 合并前必须回答 4 个问题（与 ADR-0180 同构）：

1. **业务方 ≤ 1 行 + typed payload + 鉴权声明**：业务方能否只调一行 `EventMechanism.send(SpineEventPayload(execution_point="spine.cognition.brain.perceive.start", channel="fact", payload={"state_id": ...}), plugin=RefClass)`？
2. **鉴权白名单按设计工作**：未在 yaml `publishers` 白名单的 plugin 调 `send()` → raise `UnauthorizedPublish`；未在 `subscribers` 白名单的 plugin 调 `subscribe()` → raise `UnauthorizedSubscribe`。
3. **消费者偷听防护**：plugin A subscribe `spine.cognition.brain.perceive.*`，机制按 yaml 路由；plugin B 试图 subscribe `spine.runtime.*` 但 yaml 未授权 → raise。
4. **plugin manifest 与 yaml SSOT 互校验**：plugin manifest `event_publishes=["spine.cognition.brain.perceive.start"]` 但 yaml 未列该 plugin → boot 失败。

4 个问题都通过 → 试点锁定，进入 PR 2–13 灰度。

## 风险与回滚

- **风险 1**：spine 影响面比 events 大（76 EP 跨 5 层 + cursor / reducer / projection_host 三个耦合点）。**缓解**：试点只 1 EP + 1 publisher + 1 sink + 1 subscriber；后续 PR 逐 EP 推。
- **风险 2**：hash chain 从机制剥离到 sink，落盘失败时 chain 字段可能不一致。**缓解**：`spine_chain_sink` 与 `file_sink` 同事务写入；试点 PR 必加 chain 完整性测试。
- **风险 3**：FD-1/FD-2 升级为 EventMechanism 通用语义，可能影响 events 试点（ADR-0180 业务方）行为。**缓解**：机制 D6 必加 0180 试点业务方回归测试（`tests/plugins/events/publishers/test_delegation_cache.py` 必须仍全过）。
- **回滚**：试点 PR 不删旧 `EventSpine` / reflector / sink / deriver 任何文件，回滚 = 撤回试点 PR 即可。
