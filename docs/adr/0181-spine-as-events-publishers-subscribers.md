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
- **PR-2 增强：category 自动派生**。`payloads_spine.py` 内 `_SPINE_EP_TO_CATEGORY: dict[str, str]`（16 EP → category 映射，目前 cognition 全量），`SpineEventPayload.model_validator(before)` 从 `execution_point` 自动派生 `category`。**业务方只传 `execution_point`，不传 `category`**——category 不再由业务方构造，避免"业务方任意伪造 category 走鉴权矩阵"的协议层风险；机制仍按 `payload.category` 鉴权，但 `category` 是壳类派生、不可被业务方改写。EP 增则映射表 + yaml 同 PR 加；EP 删则映射表保留到 PR-9 旧 spine 全退役。
- **PR-2 增强：`SpineChainContext` 无状态 chain**。`spine_runtime.SpineChainContext` 把 chain 上下文（`prev_hash`，单一字段）从 sink 的类级可变状态（`_last_hash`）提到一个 sink 自维护的上下文对象里——`SpineChain` 本身是纯函数（`prev_hash` 显式传入），不持状态；sink 持有一个 `SpineChainContext` 实例，每次 `append` 时传入 `SpineChain.next_hash(prev, causality_id)` 得新 hash。**`sequence` / `epoch` 由 `EventMechanism` 在 `send()` 路径上注入（见 `EventRef`），不进入 `SpineChainContext`**——helpers 层不重复持有机制层字段。**协议层不变**：FD-1 sink 失败语义仍由 `EventMechanism` 通用失败语义（D4 + 机制 D6）保证；chain 完整性测试要求 chain 字段在 sink 失败时一致（见风险 2 缓解）。

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

### D6. `_SPINE_EP_TO_CATEGORY` 自动派生：壳类对外只露 `execution_point`

> 见 D2 中"PR-2 增强"段。要点：业务方构造 `SpineEventPayload(execution_point=..., ...)` 即可，`category` 由壳类 model_validator 从 `_SPINE_EP_TO_CATEGORY` 自动派生，业务方**不能**显式传 `category`、**不能**靠伪造 category 绕过鉴权。机制仍按 `payload.category` 鉴权——SSOT 唯一来源是 `_SPINE_EP_TO_CATEGORY` + `spine.yaml` closure。

### D7. `spine_runtime helpers` 提取层：机制与 sink/subscriber 之间的公共辅助层（PR-2 复审新增）

PR-2 复审发现试点 + PR-2 余 15 EP 共 2 个 sink（`spine_chain_sink`）+ 1 个 subscriber（`spine_step_tree_accumulator`）出现 3 类重复：① 散落的 `hasattr(payload, "x")` 类型守卫；② `spine_chain_sink` 自维护 `_last_hash` 类级可变状态 + `datetime.now(timezone.utc)` 时钟；③ 各自实现结构化记录 + 序列化。把这些重复抽到 `lca_kernel/events/spine_runtime.py`：

| helper | 职责 | 不属于它的 |
|---|---|---|
| `is_spine_event(payload) -> TypeGuard[SpineEventPayload]` | 统一类型守卫，替代散落 `hasattr` 检查 | 不做鉴权（机制 D6 负责） |
| `SpineClock.now()` / `.now_iso()` / `.freeze(at)` | 统一时钟，可 freeze（测试用） | 不做 chain |
| `SpineChain.next_hash(prev_hash, causality_id) -> str` | **无状态** chain 计算（纯函数），`prev_hash` 显式传入 | 不持类级可变状态 |
| `SpineChainContext(prev_hash)` | chain 上下文壳（sink 自维护 prev 实例；当前仅 prev_hash 字段，sequence/epoch 由机制层注入，不进 helpers） | 不做落盘路径（sink 自己管） |
| `SpineEventRecord.build(payload, ref, *, chain=...)` + `.to_dict()` | 标准化不可变记录 + 序列化 | 不做 fanout |
| `SpineStream(default=...)` + `.write(line)` | 统一流输出，可注入 stream（测试 override） | 不做订阅路由 |
| `default_chain_path()` | 落盘路径 helper；env `LCA_SPINE_CHAIN_PATH` 覆盖 | 不读 Profile（路径由 Profile 注入） |

**关键边界 — `spine_runtime` 不是机制也不是 plugin**：

- **不是机制**：`EventMechanism`（`mechanism.py`）只负责 send / subscribe / 鉴权 / 失败语义（FD-1/FD-2）；`spine_runtime` 不参与 send/subscribe 路径，不持任何"机制层状态"（无 registry、无 router、无 sender）。
- **不是 plugin**：`spine_runtime` 不在 `lca/plugins/events/` 下，不被 Profile `provides/requires` 装配，**不可被 plugin 替换**；与机制同一层（`lca_kernel/events/`），属 kernel 元层，固定。
- **不是壳类**：`payloads_spine.py` 承载 `execution_point` + `payload` + chain 字段；`spine_runtime` 只承载"所有 sink/subscriber 都要做的事"（类型守卫 / 时钟 / chain / 序列化 / 流）。

**职责边界守护**：

- `spine_runtime` **不允许** `import` 任何 sink / subscriber / publisher / plugin——helper 永远是被调用方，不调用业务方。**依赖方向由 `tool.importlinter.contracts` 第 6 条 `kernel-domain-isolation` 间接守护**：源模块（L0–L3 + `lca.plugins.*`）禁 `import lca_kernel`；`spine_runtime` 在 `lca_kernel.events` 内，`lca/plugins/events/spine_*` 要用它必须先通过契约 6 反向检查（事实上不可能），等价于"反向 import 即 fail"。当前无专门针对 `spine_runtime` 这一文件的 lint rule，若 PR-2 之后的 PR 触及 `spine_runtime` 必须复审 helper 列表与 consumer 对齐情况。
- `spine_runtime` **不允许** `import` `EventMechanism`（机制本体）——helper 不依赖机制运行时；只依赖 `SpineEventPayload` 壳类（壳类是数据，不含机制）。
- `spine_runtime` 当前消费者：`spine_chain_sink`（`SpineChain` + `SpineClock` + `SpineEventRecord` + `default_chain_path` 全走 helpers；行数随 PR-3 实际产物变化，不在本 ADR 锁具体数字）、`spine_step_tree_accumulator`（`is_spine_event()` 替换 `hasattr` 守卫）。

**删-when**：`spine_runtime` 与 `EventMechanism` 同生命周期；`spine` 完全退役（PR-9 + PR-10 完成后）才考虑是否合并入 mechanism 或保留——届时 ADR-0181 状态变更时再决策，本 ADR 不锁。

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

### 试点范围（P2 — PR-2 cognition 全迁后实际状态）

PR-2（commit `2b3643e1`）合并后实际状态：试点 1 + PR-2 余 15 = **cognition 16 EP 全迁**，旧 `lca/plugins/observability/spine/reflectors/cognition.py` 已删除。

| 项 | PR-2 后范围 |
|---|---|
| `spine.yaml` EP 行数 | **16 行**（试点 1 + PR-2 余 15） |
| `spine_reflector_cognition` emit 数 | **16 个**：`brain.{perceive,think,gate}.{start,end}`（6）+ `critic.eval.{start,end}`（2）+ `reasoner.reason.{start,end}`（2）+ `prompt_assembler.assemble.{start,end}`（2）+ `synthesizer.merge`（1）+ `skill_router.route`（1）+ `memory.{read,write}`（2）|
| `payloads_spine.py` 闭集 | 16 EP；`_SPINE_EP_TO_CATEGORY` 映射；`model_validator(before)` 从 `execution_point` 自动派生 `category`（业务方只传 EP，不传 category） |
| `contracts/event.py` `Category` enum | 加 15 个 `SPINE_COGNITION_*`；`CATEGORY_DEFAULT_PLANE` 加 15 个 OBSERVABILITY 映射 |
| 调用方零改动 | `reasoner` / `synthesizer` / `skill_router` / `null_critic` / `modular_brain` / `simple_memory` 6 个 cognition 调用方：emit signature 严格对齐旧 reflector，零改动 |
| 旧 cognition reflector | `lca/plugins/observability/spine/reflectors/cognition.py` 删除 |
| `_spine_envelope` 装饰器 | import 路径改 `lca.plugins.events.publishers.spine_reflector_cognition` |
| `spine_runtime helpers` 提取层 | `lca_kernel/events/spine_runtime.py`（见 D7）|
| 试点盖章判定 | 4 条全过；PR-2 余 15 EP 由 `spine.yaml` 16 行 + 16 enum + 16 emit + `_SPINE_EP_TO_CATEGORY` 完整覆盖 |

## 迁移 PR 切分（PR-2 已合并，余 9 PR 推进中）

PR-2（commit `2b3643e1`）合并 §迁移 PR 切分 PR-2 + PR-7 余 cognition = cognition 16 EP 全迁 + `spine_runtime helpers` 提取层。下方表为 PR-2 后重排的 10 PR 视图（试点 PR = 已落 1 个 EP + 机制 D6 + 壳类 + 1 publisher/sink/subscriber）：

| PR | 状态 | 范围 | 删-when |
|---|---|---|---|
| 试点 PR | ✅ 合并 | 机制 D6 + SpineEventPayload + 1 yaml 行 + 1 publisher + 1 sink + 1 subscriber | — |
| 2 | ✅ 合并（`2b3643e1`）| cognition 16 EP 全迁（旧 PR-2 余 13 EP + 旧 PR-7 余 cognition 部分合并而来）+ spine_runtime helpers 提取层（D7）| `rg "emit_brain_\|emit_critic_\|emit_reasoner_\|emit_prompt_assembler\|emit_synthesizer\|emit_skill_router\|emit_memory_" lca/plugins/observability/spine/ = 0` ✅ |
| 3 | ✅ 合并（`67fbbd6e`）| `spine.yaml` 补 body_llm / runtime / exception 18 个 category + body_llm + runtime reflector 全迁 + 业务方 7 文件迁移收尾（safe_executor / action_handlers / envelope_emitter / llm adapters / runtime_loop / reducer / runtime_lifecycle_emitter）| 旧 `reflectors/body_llm.py` + `reflectors/runtime.py` 已删 |
| 4 | 待启 | `spine.yaml` 补 agent_spawn EP + agent_spawn reflector 迁 + ADR-0169 cursor 改造为 subscriber（`coord.emit_phase` 删，与 ADR-0180 PR-15 同步） | 旧 agent_spawn reflector 删 |
| 5 | 待启 | `spine.yaml` 补 transport / context / signature / source reflector EP（注意：4 个 reflector 是 L0 FieldProducer / marker capability，不是 EventMechanism publisher；可能 0 个新 category — 实施时复核 ADR-0181.x）| 旧 transport / context / signature / source reflector 删 |
| 6 | 待启 | spine sinks 余下部分全迁（routing_file_sink / tracing_file_sink / otel_trace；`spine_chain_sink` 已 PR-2 / PR-3 走 `spine_runtime` helpers 重构） | `rg "from lca.infrastructure.observability.spine.sinks" lca/ = 0` |
| 7 | 待启 | spine derivers 余下全迁（graph / waterfall / narrative / live_tail；`spine_step_tree_accumulator` 已 PR-2 用 `is_spine_event()` 重构） | `rg "from lca.infrastructure.observability.spine.derivers" lca/ = 0` |
| 8 | 待启 | 旧 `event_spine.py` / `event_record.py` / `manifest.py` / `compile_spine_registry` 删除 | `rg "EventSpine\b" lca/ = 0` 且 `rg "compile_spine_registry" lca/ = 0` |
| 9 | 待启 | 旧 `_spine_safety.py` 删除（`safe_append` / `set_active_spine` / `get_active_spine` 退役）+ writable_matrix 改走 `EventMechanism.send(..., plugin=WritableMatrixPlugin)` + ProjectionHost（ADR-0170）改走 `EventMechanism.subscribe` + reducer 改造为 subscriber（不再写 state；改 subscribe `gate.*`）| `rg "safe_append\|set_active_spine\|writable_matrix.append\|spine\.append\|spine_core\.append\|emit_through_pipeline" lca/ = 0`（含 PR-3 子任务 7 发现的 stale grep 模式）|
| 7 | 待启 | spine sinks 余下部分全迁（routing_file_sink / tracing_file_sink / otel_trace；`spine_chain_sink` 已在 PR-2 走 `spine_runtime` helpers 重构） | `rg "from lca.infrastructure.observability.spine.sinks" lca/ = 0` |
| 8 | 待启 | spine derivers 余下全迁（graph / waterfall / narrative / live_tail；`spine_step_tree_accumulator` 已在 PR-2 用 `is_spine_event()` 重构） | `rg "from lca.infrastructure.observability.spine.derivers" lca/ = 0` |
| 9 | 待启 | 旧 `event_spine.py` / `event_record.py` / `manifest.py` / `compile_spine_registry` 删除 | `rg "EventSpine\b" lca/ = 0` 且 `rg "compile_spine_registry" lca/ = 0` |
| 10 | 待启 | 旧 `_spine_safety.py` 删除（`safe_append` / `set_active_spine` / `get_active_spine` 退役）+ writable_matrix 改走 `EventMechanism.send(..., plugin=WritableMatrixPlugin)` + ProjectionHost（ADR-0170）改走 `EventMechanism.subscribe` + reducer 改造为 subscriber（不再写 state；改 subscribe `gate.*`）| `rg "safe_append\|set_active_spine\|writable_matrix.append" lca/ = 0` |

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
- **风险 4**：`spine_runtime helpers` 提取层职责边界被侵蚀（PR-2 复审发现重复 → 抽取；若 helpers 越界 import sink/subscriber/plugin 或机制，会把 helpers 变成平行机制）。**缓解**：helpers 不允许 import 任何 sink/subscriber/plugin；`spine_runtime` → `lca/plugins/events/` 反向依赖由 `tool.importlinter.contracts` 第 6 条 `kernel-domain-isolation` 间接守护（源模块禁 `import lca_kernel`；`spine_runtime` 在 `lca_kernel.events` 内，反向 `import` 即撞契约 6）；`spine_runtime` 不 import `EventMechanism`；与机制同生命周期（PR-9 + PR-10 完成后才评估是否合并）。
- **回滚**：试点 PR + PR-2 不删旧 `EventSpine` / reflector 余 7 文件 / sink 余 3+ 文件 / deriver 余 7 文件，回滚 = `git revert 2b3643e1 71d76d27` 即可恢复 spine 旧机制。
