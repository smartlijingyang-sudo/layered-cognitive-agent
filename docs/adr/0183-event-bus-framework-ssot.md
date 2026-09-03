# ADR-0183 — 事件总线框架：可组合、可配置、可插拔 + 单 SSOT

## 状态

Accepted（2026-09-03 落地完成）。

**主分支 `back-ui-821-other-keep` 已合并**：

| Merge commit | 内含 PR | 合并日期 |
|---|---|---|
| `d439ece8` | PR-A（`events.jsonl` 字面量 SSOT sweep）+ PR-D（文档/附录 note 收口）| 2026-09-03 |
| `0a816748` | PR-B（EventMechanism 全收口 + `mechanism.py` 整文件删除）| 2026-09-03 |
| `79b20b73` | PR-C（legacy reader 全迁 `SpineReader` + xfail 改 strict）| 2026-09-03 |

12 PR 全部落地：PR-1~12 的 commit hash 与 delete-when 验收见 §5.2 + §B.2。架构不变量 `tests/architecture/test_event_bus_invariants.py` **8 passed, 0 xfailed**（2026-09-03 验证）。

**遗留债务（非阻塞,已记入后续 ADR）**：

- PR-3 `FieldType` 字符串化：`EventSpec.fields` 仍是 `dict[str, str]`,yaml 字段类型未做运行时校验。101 个 category 已全部绑定 typed `payload_class`（`EventRegistry.payload_by_category` SSOT）。运行期正确性不受影响,留作下一个 ADR 单独做字段类型化增量。
- `loop_cursor/_spine_port.py:WritePort` 是 cursor 写 spine 的 facade（PR-9 设计）,与 EventBus.publish 并行存在,符合 I-FW-BUS-1 的"业务不绕 facade 直调 EventSpine"严格断言。

## 0. 决策摘要

把 ADR-0167（spine SSOT）/ 0170（writable matrix）/ 0172（observability exporters）/
0175（prompt trace）/ 0176（step-tree deriver）/ 0177（EnvelopeEmitter）/ 0178（4 级
收敛）/ 0180（v2 event-layer pilot）/ 0181（spine as publishers/subscribers）/ 0182
（EventMechanism 框架化）共 10 篇合并为**单 ADR**，吸收为一个新的「事件总线框架
+ 单 SSOT 落盘链 + 声明式编排」。

理由：10 篇 ADR 各自打补丁形成循环——每篇 PR 暴露前一篇的隐藏 bug，根因是缺少
**单点真值 + 单点编排机制**。本 ADR 一次性收敛：

- 单一事件总线 `EventBus`（机制壳 + 4 个 hook 协议）
- 单一落盘链 `<run_id>.spine.jsonl`（事实链 SSOT）
- 单一状态机 `RunLifecycleStatus`（状态 SSOT）
- 单一协议 `EnvelopeEmitter[T]` + `EventPayload` 子类（类型化 SSOT）
- 单一编排层 `Pipeline`（声明式 YAML 配置 hook、sink、subscriber）

生产者和消费者可声明自定义 plugin、可插拔，但 **SSOT 不让步**：plugin 不能改总线
内部、不能改 record 字节布局、不能改状态机 enum。

落地进度：12 PR 见 §5.2(已合入 worktree,见每条 commit hash);附录 A/B/C note 状态见 §10。

## 1. 背景与现状（事实）

### 1.1 现有 ADR 状态清单

| ADR | 完成状态 |
|---|---|
| 0167 spine SSOT | Accepted |
| 0170 writable matrix | Accepted |
| 0172 exporters | Accepted |
| 0175 prompt trace | Accepted |
| 0176 step-tree deriver | Accepted |
| 0177 EnvelopeEmitter | Accepted |
| 0178 4 级收敛 | Proposed |
| 0180 v2 event-layer pilot | Reverted |
| 0181 publishers/subscribers | Accepted |
| 0182 EventMechanism 框架化 | Proposed |

### 1.2 当前事件消费链路（实测）

```
reducer.apply_*            ─┐
cursor.begin_step/record_*  ─┤── reflector publisher (×21 manifest,15 unique) ──→ EventMechanism.send
runtime_loop except block  ─┤                                          │
CoordAdapter.append         ─┘                                          ↓
                                                                EventMechanism
                                                                ├─ _subscribers (FD-2)
                                                                └─ _sinks (FD-1, 代码无人走)
                                                                          ↓
                                                              SpineChainSink 落盘
                                                              SpineFileSink 落盘
                                                              JournalSink (死插件,装载即抛)
                                                                          ↓
                                                              <run_id>.spine.jsonl
                                                              <run_id>.events.jsonl (legacy)
                                                              FileSink 双 fd
                                                                          ↓
                                                              _capture_io / projector / step-tree
                                                              → UI / SSE / diagnostic
```

### 1.3 yaml 注册表现状（实测）

| 项 | 值 |
|---|---|
| 文件 | `lca_kernel/events/config/observability/spine.yaml`(1614 行) + `business/team.yaml`(25 行) |
| category 总数 | 101(100 spine.* + 1 team.delegation.cache_hit) |
| publisher class(去重) | 15 |
| subscriber/sink class(去重) | 3(`SpineChainSink`、`ConsoleProjectorSubscriber`、`SpineStepTreeAccumulator`) |
| `subscribers:` 块 | 100(每个 category 1 块) |
| `default_subscribers:` 块 | 100(同上;在 `mechanism.py:223` fanout **不被读取**) |
| 死插件 | `lca/plugins/events/sinks/journal/`(装载即抛:`spine.yaml` 授权 1/101) |
| 反推 record + silent fallback | `spine_file_sink/sink.py:50-77`(`_build_event_record` + 2 处 `except ValueError`) |
| `EventSpec.fields` 类型 | `dict[str, str]`(字符串字典,发错类型落盘才发现) |
| `EventRef.trace_id` | 全空(`mechanism.py:122`) |
| 自指派观察 | 无 |

### 1.4 prefix 分布(101 category,实测)

| prefix | 数量 | 主要 publisher |
|---|---:|---|
| spine.cognition | 16 | ReflectorCognition |
| spine.phase | 12 | ReflectorPhase |
| spine.control | 11 | ReflectorControl |
| spine.runtime | 6 | ReflectorRuntime |
| spine.perception | 6 | ReflectorPerception |
| spine.llm | 5 | ReflectorBodyLlm |
| spine.body | 5 | ReflectorBodyLlm |
| spine.kernel | 3 | ReflectorKernelLoop |
| spine.boot | 3 | ReflectorBoot |
| spine.team | 7 | ReflectorTeam |
| spine.writable | 7 | WritableMatrixPlugin + ReflectorWritable |
| spine.agent | 3 | ReflectorAgentSpawn |
| spine.agent_loop | 2 | ReflectorAgentSpawn |
| spine.phase_graph | 4 | ReflectorPhaseGraph |
| spine.transport | 3 | ReflectorTransport |
| spine.exception | 2 | ReflectorRuntime |
| spine.perceive | 1 | ReflectorCognition |
| spine.loop | 1 | LoopCursorPlugin |
| spine.lifecycle | 1 | ReflectorRuntime |
| team.delegation | 1 | DelegationCachePlugin |

### 1.5 producer 端 emit 现场（实测）

| 文件 | 调用 | 现状 |
|---|---|---|
| `lca/runtime/reducer.py:73-118` | `_instrument_apply` 装饰器 → `emit_runtime_reducer_apply_{start,end}` | 通过 spine_reflector_runtime publisher 发 |
| `lca/infrastructure/observability/loop_cursor/coordinator_adapter.py:137-300+` | `coord.begin_step / end_step / record_* / emit_phase / emit` | `emit_phase` 已 raise `NotImplementedError`;业务路径仍用 `coord.begin_step / record_*` 双写 |
| `lca/runtime/runtime_loop.py:281,296` | `emit_exception_caught(boundary, exc_type, message, trace_id)` | 4 键裸 dict,`EnvelopeEmitter` Protocol 已支持 `record`,runtime_loop 未迁 |
| `lca/infrastructure/observability/spine/event_spine.py:60` | `append(payload)` | cursor 写 spine 的唯一事实写入点 |
| `lca/infrastructure/observability/loop_cursor/bind.py:80` | `append(**kw)` | 上层 facade |

### 1.6 状态机三套并存(实测)

| enum | 定义 | 引用数 | 范围 |
|---|---|---:|---|
| `RunStatus` | `lca/infrastructure/observability/journal/engine/reducer.py:22` | 39(35 实际 + 4 README/test) | webserver session 私有 |
| `JournalRunStatus` (= `RunStatus` 别名) | `lca/plugins/transport/webserver/handlers/runs/terminal/status.py:10` | 5 | journal reducer 私有别名 |
| `RunLifecycleStatus` | ADR-0178 §L1 已规划,**代码内尚无 class 定义** | 0 | contracts 层(本 ADR 落地) |

`webserver/handlers/runs/terminal/status.py:52-59` 有 `journal_to_session_status` 映射表——这是状态机三套并存的活标本。

### 1.7 现状痛点(10 类根因)

1. **3 入口并存** — `subscribe` + `register_sink` + `send`;FD-1 代码无人走
2. **2 处 sink 反推 record fallback** — `_build_event_record` + 2 处 `except ValueError` 静默记错
3. **journal sink 装载即抛** — yaml 授权 1/101,manifest 仍批量订阅
4. **yaml 100 处 `subscribers:` + 100 处 `default_subscribers:`** — 1614 行 yaml;`default_subscribers` 仅 1 处读者
5. **`default_subscribers` 死配置** — 仅 1 处读者(测试断言子集关系),fanout 实际只用运行时 `subscribe()`
6. **payload `dict[str, str]`** — 字符串字典,发错类型落盘后才发现
7. **`trace_id=""` 全空** — 两套 trace(Langfuse exporter 与 spine)并存
8. **3 套状态机 enum** — `RunStatus`、`JournalRunStatus`、`RunLifecycleStatus`(未落地)
9. **runtime_loop 4 键裸 dict** — `emit_exception_caught(boundary, exc_type, message, trace_id)`
10. **16 处 `coord.emit_phase` + cursor `record_*` 双写** — ADR-0181 执行债

## 2. 第一性原理（机制,不是补丁）

### 2.1 真正发生的只有两件事

- **发送事件**:业务代码要在某时点把一段事实落盘 + 让派生系统看见
- **消费事件**:业务代码要在某时点对某类事实做响应

### 2.2 最干净的形态

```
                    ┌──────────────────────────┐
                    │ Pipeline (声明式编排)      │  ← Profile/Bundle 装配
                    │ - hooks: [HookSpec, ...]  │     可配置、可组合
                    │ - sinks: [SinkSpec, ...]  │
                    │ - rules: [RuleSpec, ...]  │
                    └──────────────────────────┘
                              │
                              ↓ 装配成
                    ┌──────────────────────────┐
                    │ EventBus (机制壳)         │  ← 框架自带,plugin 不可改
                    │ - publish / subscribe     │     鉴权 / 路由 / 校验 / SSOT
                    │ - 4 hook 协议调用点        │     通过 Pipeline 配置
                    └──────────────────────────┘
                              │
                              ↓ 落盘
                    ┌──────────────────────────┐
                    │ SpineSink (事实链 SSOT)   │  ← <run_id>.spine.jsonl
                    │ - to_dict() 字节布局 SSOT │     plugin 可换实现
                    │ - fsync 策略 = hook       │     但接口必须遵守
                    └──────────────────────────┘
                              │
                              ↓ 派生
                    ┌──────────────────────────┐
                    │ SpineReader + Derivers    │  ← 单一事实入口
                    │ - ProjectionDeriver       │     JournalProjection
                    │ - StepTreeDeriver         │     StepTree
                    │ - ExporterHook            │     Langfuse/OTel
                    └──────────────────────────┘
```

**核心约束**:

| 层 | 谁拥有 | 谁可改 |
|---|---|---|
| EventBus 内部 | 框架 | 框架 |
| SpineSink 字节布局 | 框架(`SpineEventRecord.to_dict()`) | 框架 |
| Pipeline 编排 | Profile/Bundle | Profile author |
| Hook 实现 | Plugin | Plugin |
| Sink 后端实现 | Plugin | Plugin(实现 `SinkBackend` 协议) |
| 派生 deriver | Plugin | Plugin |
| Reader 实现 | 框架(`SpineReader`) | 框架 |

**plugin 可控 = 可组合、可配置、可插拔,但必须在 5 条不变量的约束下**(见 §4)。

### 2.3 用户诉求的机制对应

| 诉求 | 机制形态 |
|---|---|
| 一切节点可控 | **Pipeline 声明式 YAML** —— Profile 决定每个节点装什么 hook、什么 sink |
| 自定义逻辑可插 | **4 个 hook Protocol** + **SinkBackend 协议** + plugin manifest |
| 链路中间信息畅通 | **EventPayload 子类强制** + **EventRef 强制注入** + **`lca-ops inspect-pipeline`** |
| 约束与不变性 | **5 条 I-FW 不变量 + 架构测试守护** |
| 可配置可编排组合式 | **Pipeline YAML**(按 profile 装载) |
| SSOT 是唯一配置 | **3 个 SSOT**(事实链 / 状态机 / payload schema)+ 其它全派生 |
| 落盘可换 | **SinkBackend 协议** + SpineSink 是默认实现 |
| 何时可换 | **Pipeline sinks: 段** 决定装载哪些后端 |

## 3. 设计

### 3.1 总线入口(producer 唯一暴露)

```python
# lca_kernel/events/bus.py —— 框架自带

class EventBus(Generic[P]):
    """LCA 事件总线唯一入口。

    协议:
    - producer 调 publish(payload, *, producer=…)
    - consumer 调 subscribe(*, plugin, on_event, failure=…)
    - sink 走 subscribe(failure=fail_fast)
    - subscriber 走 subscribe(failure=contained)

    自定义逻辑走 Pipeline 配置 + 4 个 hook 协议(plugin 实现 + manifest 注册)。
    """

    def publish(
        self,
        payload: EventPayload,
        *,
        producer: type,
        trace_id: str | None = None,
    ) -> EventRef:
        """唯一发送入口。

        流程:
        1. 鉴权 producer is can_publish(category)
        2. 查 spec = registry.spec_for(category)
        3. 跑 pre_dispatch hooks
        4. 校验 payload schema(spec.fields)
        5. 构造 EventRef(注入 trace_id from contextvars)
        6. fanout: sinks(FD-1) → consumers(FD-2)
        7. 跑 post_dispatch hooks
        8. 跑 failure hooks(若 consumer 抛错)
        9. 返回 EventRef

        失败语义:
        - UnauthorizedPublishError: producer 不在白名单(FD-1,抛给调用方)
        - PayloadSchemaError: payload 与 spec 不符(FD-1,抛给调用方)
        """

    def subscribe(
        self,
        *,
        plugin: type,
        category: Category | str,
        on_event: Callable[[EventPayload, EventRef], None],
        failure: FailureSemantics = FailureSemantics.CONTAINED,
    ) -> ConsumerHandle:
        """唯一消费入口。

        失败语义:
        - failure=fail_fast → sinks[category].append(...)
        - failure=contained → consumers[category].append(...)
        - 必须 plugin in registry.consumers(category),否则 UnauthorizedConsumeError
        - 返回 ConsumerHandle 用于 unregister(框架预留,本 ADR 不实装,见 §4.2)
        """

    def register_pipeline(self, pipeline: Pipeline) -> None:
        """装载声明式编排(Profile 启动时调用一次)。
        装载后不可热替换(按 YAGNI;若需要,见 §5 后续 ADR)。
        """
```

### 3.2 4 个 hook 协议(plugin 实现)

```python
# lca_kernel/events/hooks.py —— 框架自带 4 个 hook Protocol

class PreDispatchHook(Protocol):
    """publish() 入口处:plugin 可改 payload / 校验 / 注入 context。

    返回 None 继续;返回 SkipDispatch → 跳过本事件(不发、不落盘);
    返回新 EventPayload → 替换原 payload。
    """
    def before_publish(
        self, payload: EventPayload, producer: type, ctx: PublishContext
    ) -> EventPayload | SkipDispatch: ...

class SpecResolverHook(Protocol):
    """机制找不到 spec 时,plugin 可提供;返回 EventSpec 即注册。"""
    def resolve_spec(self, category: Category) -> EventSpec | None: ...

class PostDispatchHook(Protocol):
    """dispatch 完成后(所有 consumer 跑完),plugin 可派生事件 / 跨 EP 关联。

    返回 0..N 新事件 → 走 bus.publish 再次进入总线。
    """
    def after_dispatch(
        self, payload: EventPayload, ref: EventRef, results: list[ConsumerResult]
    ) -> Iterable[EventPayload]: ...

class FailureHook(Protocol):
    """consumer 抛错时,plugin 可补偿 / 改 failure semantics / 写自定义 metric。

    默认实现 = 吞错 + 发 event.bus.dispatch.consumers.end。
    """
    def on_consumer_failure(
        self, payload: EventPayload, ref: EventRef, exc: BaseException
    ) -> FailureAction: ...
```

**hook 通过 Pipeline 编排装载,不在代码里写死**。

### 3.3 Pipeline 声明式编排(用户「可控可配置」的核心载体)

```yaml
# profiles/event-pipeline/web-standard.yaml
pipeline:
  name: web-standard-event-pipeline
  version: 1

  # ====== A. hooks(自定义逻辑) ======
  hooks:
    - id: trace-context-injection
      hook: lca_kernel.events.hooks.TraceContextHook
      stage: pre_dispatch
      config:
        trace_id_source: contextvars

    - id: payload-schema-validation
      hook: lca_kernel.events.hooks.PayloadSchemaHook
      stage: pre_dispatch
      config:
        fail_fast_on_missing_field: true

    - id: model-visible-capture
      hook: lca.plugins.observability.hooks.ModelVisibleHook
      stage: pre_dispatch
      config:
        capture_prompts: true
        capture_categories: ["spine.llm.", "spine.cognition."]

    - id: mechanism-self-observation
      hook: lca_kernel.events.hooks.MechanismDispatchObserver
      stage: post_dispatch
      config:
        emit_event_sinks: event.bus.dispatch.sinks.end
        emit_event_consumers: event.bus.dispatch.consumers.end

    - id: consumers-failure-default
      hook: lca_kernel.events.hooks.DefaultFailureHook
      stage: on_failure
      config:
        emit_event: event.bus.dispatch.consumers.end
        swallow: true

    - id: langfuse-exporter
      hook: lca.plugins.observability.exporters.langfuse.LangfuseExporterHook
      stage: post_dispatch
      config:
        host: "${from_env: LANGFUSE_HOST}"
        public_key: "${from_env: LANGFUSE_PUBLIC_KEY}"
        secret_key: "${from_env: LANGFUSE_SECRET_KEY}"

  # ====== B. sinks(落盘后端) ======
  sinks:
    - id: spine-fact-chain
      backend: lca_kernel.events.sinks.SpineSink
      failure: fail_fast
      config:
        path_template: "{run_id}.spine.jsonl"
        fsync_strategy: batch
        fsync_batch_size: 100
        fsync_interval_ms: 50
        checksum_on_open: true

    - id: spine-remote-mirror         # 可选:派生链镜像
      backend: lca.plugins.events.sinks.remote_replicator.RemoteReplicatorSink
      failure: contained
      config:
        target: "kafka://lca.spine.events"
        depends_on: spine-fact-chain    # fact chain 成功后才走
        compression: zstd

  # ====== C. consumer rules(路由) ======
  consumer_rules:
    # 认知平面:contain 失败语义,允许部分派生失败
    - prefix: "spine.cognition."
      consumers:
        - plugin: lca.plugins.events.subscribers.console_projector.subscriber.ConsoleProjectorSubscriber
          failure: contained

    # 模型可见事实:必须落盘(fail_fast)
    - prefix: "spine.llm."
      consumers:
        - plugin: lca.plugins.events.subscribers.model_visible_writer.subscriber.ModelVisibleWriter
          failure: fail_fast

    # 异常事实:必须 fail_fast 落盘
    - prefix: "spine.exception."
      consumers:
        - plugin: lca.plugins.events.subscribers.exception_index_writer.subscriber.ExceptionIndexWriter
          failure: fail_fast

    # 派生 phase 事实:contain 即可
    - prefix: "spine.phase."
      consumers:
        - plugin: lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber.SpineStepTreeAccumulator
          failure: contained

    # writable matrix:fail_fast,关键事实
    - prefix: "spine.writable."
      consumers:
        - plugin: lca.plugins.events.subscribers.writable_persist.subscriber.WritablePersist
          failure: fail_fast

    # 通用兜底:所有 spine.* 落 spine-fact-chain
    - prefix: "spine."
      consumers:
        - plugin: lca.plugins.events.sinks.spine_chain_sink.sink.SpineChainSink
          failure: fail_fast

    # 团队委派业务
    - prefix: "team."
      consumers:
        - plugin: lca.plugins.events.subscribers.team_bus.subscriber.TeamBus
          failure: contained

    # 框架自观察事件:I-FW-BUS-4 守护,业务不订阅
    # (默认空 list;架构测试断言 event.bus.dispatch.* 不在 consumer_rules 内)
```

**Pipeline 装配 = Profile 启动时调 `bus.register_pipeline(pipeline)`**。

### 3.4 SinkBackend 协议(落盘可换)

```python
# lca_kernel/events/sinks/__init__.py —— 框架自带

class SinkBackend(Protocol):
    """落盘后端协议。

    SpineSink 是默认实现(事实链 SSOT)。
    plugin 可实现其它后端(KAFKA / S3 / 自研),但必须实现同一接口。
    """
    def append(self, record: SpineEventRecord) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...

class SpineSink(SinkBackend):
    """事实链 SSOT 实现。plugin 不可改 to_dict() 字节布局。

    COMPAT(AGENTS.md §1): 历史 events.jsonl 链在 I-FW-SSOT-1 守护下删除。
    """
    def append(self, record: SpineEventRecord) -> None:
        line = record.to_dict()  # SSOT —— 不可改
        self._fd.write(json.dumps(line, sort_keys=True))
        self._maybe_fsync()
    ...
```

**plugin 可换实现**:
- `RemoteSpineSink` —— 同 `to_dict()` 字节布局,不同 fs/网络后端(S3 / NFS)
- `RemoteReplicatorSink` —— 派生链镜像,显式声明 `failure: contained` + `depends_on: spine-fact-chain`

**plugin 不可改**:to_dict() 字节布局、`<run_id>.spine.jsonl` 文件名、fsync 时机约束。

### 3.5 单 SSOT — 事实链

**字节布局 SSOT** = `SpineEventRecord.to_dict()`(LCA 单一来源)

```python
# lca/infrastructure/observability/spine/event_record.py —— 框架自带
@dataclass(frozen=True)
class SpineEventRecord:
    schema_version: int           # 永远 = 1
    event_id: EventId
    category: Category
    plane: Plane
    payload: dict[str, JSONValue] # to_dict() 序列化结果,SSOT
    ref: EventRef                 # trace_id, ts, producer
    chain: ChainMeta              # predecessor / context

    def to_dict(self) -> dict[str, JSONValue]:
        """字节布局 SSOT —— plugin 不可改。"""
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "category": self.category.value,
            "plane": self.plane.value,
            "payload": self.payload,
            "ref": {
                "event_id": self.ref.event_id,
                "trace_id": self.ref.trace_id,
                "ts": self.ref.ts,
                "producer": self.ref.producer.__qualname__ if self.ref.producer else None,
            },
            "chain": dataclasses.asdict(self.chain) if self.chain else {},
        }
```

**单 SSOT 链** = `<run_id>.spine.jsonl`

- `SpineSink` 唯一写者(I-FW-SSOT-1)
- `SpineReader` 唯一读盘者
- `events.jsonl` legacy 删除(已部分完成,test_no_dual_sink 守护)
- journal sink 删除(PR-4 已规划)
- FileSink 双 fd 合并为一个 spine fd

### 3.6 单 SSOT — 状态机

```python
# lca/contracts/observability/status.py —— 框架自带,plugin 不可改

class RunLifecycleStatus(str, Enum):
    """LCA 状态机唯一 enum。

    范围:
    - PENDING: 已创建,未启动
    - RUNNING: 运行中
    - PAUSED: 暂停(等待用户输入 / 审批)
    - COMPLETED: 正常完成
    - FAILED: 失败
    - CANCELLED: 用户取消
    - TIMEOUT: 超时(从 JournalRunStatus 吸收)
    """
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
```

`EnvelopeEmitter.emit_status_change(status: RunLifecycleStatus)` —— Protocol 用 enum 而非 str。

**收口路径**:
- `RunStatus`(webserver session 私有) → 改类型为 `RunLifecycleStatus` 别名(过 PR-11.1)
- `JournalRunStatus`(journal reducer 私有) → 改类型为 `RunLifecycleStatus` 别名(过 PR-11.2)
- `_map_finish_status` 与 `journal_to_session_status` 映射表 → 全部删除(PR-11.3)
- `_instrument_apply` 中字面 `outcome` 字符串 → 改用 `RunLifecycleStatus` 枚举

### 3.7 单 SSOT — 类型化 payload

```python
# lca_kernel/events/registry.py —— 框架自带

class FieldType(str, Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    JSON = "json"
    EVENT_REF = "event_ref"

class Plane(str, Enum):
    OBSERVABILITY = "observability"
    STRUCTURAL = "structural"
    CONTROL = "control"              # 新增:runtime/control 事件归此
    DERIVED = "derived"              # 新增:phase_graph/deriver 派生事件归此

@dataclass(frozen=True)
class EventPayload:
    """所有 payload 必须继承此类。"""
    category: Category

@dataclass(frozen=True)
class EventSpec:
    category: Category
    plane: Plane
    payload_class: type[EventPayload]
    fields: dict[str, FieldType] = field(default_factory=dict)
    span_kind: SpanKind | None = None     # 接入点,本 ADR 不实装

# 已有 EventPayload 子类必须重写:
# - lca_kernel.events.payloads_spine.SpineEventPayload (carry-over)
# - lca_kernel.events.payloads.MechanismDispatchEventPayload (新,框架自观察)
# - lca_kernel.events.payloads.TeamDelegationCacheHit (carry-over,改基类)
# - 21 个 publisher payload class 需 type hint 继承 EventPayload
```

**每个 EP 绑定 payload dataclass**;yaml `fields: dict[str, FieldType]` 强制类型;`bus.publish()` 在 pre_dispatch hook chain 之前做 schema 校验。

### 3.8 Reader 与 Deriver(统一读取入口)

```python
# lca_kernel/events/reader.py —— 框架自带

class SpineReader:
    """事实链唯一读取入口。

    派生系统(ProjectionDeriver / StepTreeDeriver / ExporterHook)全部从 reader 派生。
    """
    def events(self, run_id: str) -> Iterator[SpineEventRecord]: ...
    def filter(self, *, category: Prefix | Category) -> Iterator[SpineEventRecord]: ...

class ProjectionDeriver:
    """JournalProjection = SpineReader 上的派生函数。"""
    def project(self, run_id: str) -> JournalProjection: ...

class StepTreeDeriver:
    """StepTree = SpineReader 上的派生函数(继承 ADR-0176)。"""
    def derive(self, run_id: str) -> StepTree: ...

class ExporterHook(PostDispatchHook, Protocol):
    """Langfuse / OTel 走 PostDispatchHook;不绑死具体 SDK。"""
    ...
```

**所有 UI / SSE / diagnostic 必须从 `SpineReader.events()` 或派生 deriver 取数据** —— 禁止直读文件。

### 3.9 trace_id 注入

```python
# lca_kernel/events/bus.py

import contextvars

_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lca_event_trace_id", default=None
)

class EventBus:
    def publish(self, payload, *, producer, trace_id=None):
        ...
        effective_trace = (
            trace_id
            or getattr(payload, "trace_id", None)
            or _current_trace_id.get()
            or new_id("trc")
        )
        ref = EventRef(event_id=new_id("evt"), trace_id=effective_trace, ...)
```

- 业务方不再传 `trace_id`(兼容旧 publisher,机制优先用 `payload.trace_id`)
- `contextvars` 由 webserver lifespan adapter 在 HTTP request 进入时 set,离开时 reset
- 自指派观察事件 `event.bus.dispatch.consumers.end` 同样带 trace_id

### 3.10 自指派观察(走 hook 协议,避免新事件类型)

```python
# lca_kernel/events/hooks.py —— 默认实现

class MechanismDispatchObserver(PostDispatchHook):
    """机制自指派观察 hook。Pipeline 装载时启用。

    事件类型:event.bus.dispatch.{sinks,consumers}.end
    走 payload_class: lca_kernel.events.payloads.MechanismDispatchEventPayload
    """
    def after_dispatch(self, payload, ref, results):
        yield MechanismDispatchEventPayload(
            category=f"event.bus.dispatch.{ref.stage}.end",
            consumer_count=len(results),
            duration_s=...,
            contained_failures=tuple(r.exc_class for r in results if r.failed),
        )
```

**`MechanismDispatchEventPayload` 继承 `EventPayload`**,走同一 register 表。`Pipeline.consumer_rules` 默认不订阅 `event.bus.dispatch.*`(I-FW-BUS-4 守护)。

## 4. 不变量(5 条)

| ID | 内容 |
|---|---|
| **I-FW-BUS-1** | 所有事件发送只能走 `EventBus.publish(payload, *, producer=…)`;reducer / cursor / runtime_loop 不允许直写 spine / 直调 sink |
| **I-FW-BUS-2** | 所有事件消费只能走 `EventBus.subscribe(*, plugin, on_event, failure=…)`;失败语义由 `failure=` 参数决定,不是入口区分 |
| **I-FW-BUS-3** | 自定义逻辑只能通过 Pipeline 编排 + 4 个 hook Protocol + SinkBackend 协议注入;plugin 不允许 import EventBus 内部或改 SpineSink 字节布局 |
| **I-FW-SSOT-1** | `<run_id>.spine.jsonl` 是事件链唯一 SSOT;`SpineSink` 唯一写、`SpineReader` 唯一读 |
| **I-FW-SSOT-2** | `RunLifecycleStatus` 是状态机唯一 enum;`RunStatus` / `JournalRunStatus` 删除 |
| **I-FW-BUS-4** | 业务方不订阅 `event.bus.dispatch.*`(Pipeline consumer_rules 不包含此 prefix) |

**架构测试**(每个 PR 合并前必跑):

```python
# tests/architecture/test_event_bus_invariants.py

def test_i_fw_bus_1():
    """reducer/cursor/runtime_loop 不允许直写 spine / 直调 sink。
    白名单:仅 lca_kernel/events/bus.py + lca_kernel/events/sinks/__init__.py
    """
    banned_patterns = [
        r"_spine\.append\(",
        r"spine_chain_sink\.",
        r"spine_file_sink\.write\(",
    ]
    for path in walk(lca, exclude=["lca_kernel/events/"]):
        for pat in banned_patterns:
            assert not rg(pat, path), f"{path} matches {pat}"

def test_i_fw_bus_2():
    """subscribe 是 consumer 唯一入口。
    旧 .subscribe( / .register_sink( 仅允许在 lca_kernel/events/ 内。
    """
    for path in walk([lca, lca_kernel, tests]):
        if "lca_kernel/events/" in path or "archive/" in path:
            continue
        assert not rg(r"\.subscribe\(", path), f"{path} has .subscribe("
        assert not rg(r"\.register_sink\(", path), f"{path} has .register_sink("

def test_i_fw_ssot_1():
    """spine.jsonl 是唯一 SSOT。events.jsonl legacy = 0。"""
    assert rg(r"events\.jsonl", lca) == 0
    assert rg(r"events\.jsonl", profiles) == 0

def test_i_fw_ssot_2():
    """RunLifecycleStatus 是状态机唯一 enum。"""
    assert rg(r"class RunStatus\b", lca) == 0
    assert rg(r"class JournalRunStatus\b", lca) == 0

def test_i_fw_bus_4():
    """Pipeline consumer_rules 不订阅 event.bus.dispatch.*。"""
    for path in walk(profiles, glob="*.yaml"):
        cfg = yaml.safe_load(open(path))
        for rule in cfg.get("pipeline", {}).get("consumer_rules", []):
            assert "event.bus.dispatch" not in rule.get("prefix", "")
```

## 5. PR 切分(12 PR,全部独立可 revert)

### 5.1 依赖图

```
PR-1 (EventBus 骨架)
  └→ PR-2 (hook + Pipeline)
       └→ PR-3 (payload 类型化)
            └→ PR-4 (单 SSOT 链)
                 └→ PR-5 (record 单一入口)
                      └→ PR-6 (yaml 前缀规则)
                           └→ PR-7 (SinkBackend + Pipeline 装载)
                                ├→ PR-8 (reducer)
                                ├→ PR-9 (cursor)
                                └→ PR-10 (runtime_loop)
                                          ↓
                                       PR-11 (状态机)         ── 可与 PR-8/9/10 并行
                                          ↓
                                       PR-12 (trace_id + 自观察) ── 最后
```

### 5.2 PR 详情

#### PR-1 事件总线骨架

| 项 | 内容 |
|---|---|
| **目标** | 新 `lca_kernel/events/bus.py`(`EventBus.publish` / `subscribe` / `register_pipeline`);旧 `EventMechanism` 标记 deprecated |
| **新增** | `lca_kernel/events/bus.py`;`lca_kernel/events/payloads.py` 中 `EventBus` / `EventRef` / `EventPayload` / `ConsumerHandle` |
| **修改** | 21 个 publisher manifest + 9 个 subscribe 真调用方改成 `bus.publish` / `bus.subscribe` |
| **删除** | 无(只 deprecate,留 `EventMechanism` 给 PR-7 之后删) |
| **架构测试** | `tests/architecture/test_event_bus_invariants.py::test_i_fw_bus_2`(subscribe 收口) |
| **验收** | `rg "EventMechanism\.(send\|subscribe\|register_sink)" lca/ lca_kernel/` 仅命中 `lca_kernel/events/mechanism.py`(deprecated) |
| **delete-when** | PR-7 后 `rg "EventMechanism" lca/ lca_kernel/` = 0 |
| **落地 commit** | `0e71f6bb`(骨架,含 PR-1+2+3+4)+ 集成补漏 `1b8ce7a8` |

#### PR-2 4 个 hook 协议 + Pipeline 编排

| 项 | 内容 |
|---|---|
| **目标** | 4 个 hook Protocol + Pipeline 装载机制 + 默认 hook 实现 |
| **新增** | `lca_kernel/events/hooks.py`(`PreDispatchHook` / `SpecResolverHook` / `PostDispatchHook` / `FailureHook` 协议 + 默认实现);`lca_kernel/events/pipeline.py`(`Pipeline` / `HookSpec` / `SinkSpec` / `ConsumerRule` dataclass) |
| **修改** | `EventBus.publish` 调用 pre_dispatch / post_dispatch / failure hook chain |
| **删除** | 无 |
| **架构测试** | Pipeline dataclass 验证:hook 必须有 stage;stage ∈ {pre_dispatch, post_dispatch, on_failure} |
| **验收** | `lca-ops inspect-pipeline web-standard` 输出全部 hook(stub) |
| **落地 commit** | `0e71f6bb`(骨架,含 PR-1+2+3+4)+ 集成补漏 `1b8ce7a8` |

#### PR-3 类型化 payload

| 项 | 内容 |
|---|---|
| **目标** | `EventPayload` 基类 + 每个 EP 绑定 dataclass + yaml `fields: dict[str, FieldType]` + `bus.publish()` schema 校验 |
| **新增** | `lca/contracts/event.py` 中 `FieldType` enum(已有)+ `Plane` enum 扩展(CONTROL/DERIVED);`lca_kernel/events/payloads/` 子目录(每个 plane 一文件) |
| **修改** | 101 个 yaml `payload_class` 字段必填;21 个 publisher payload 类型化 |
| **删除** | 无 |
| **架构测试** | `rg "payload={[^}]*}" lca/runtime/` = 0(无裸 dict);yaml `fields:` 字段必须是 `FieldType` enum 值 |
| **验收** | yaml schema 校验通过;`lca-ops validate-events web-standard` exit 0 |
| **落地 commit** | `0e71f6bb`(骨架,含 PR-1+2+3+4) |

#### PR-4 单 SSOT 链

| 项 | 内容 |
|---|---|
| **目标** | `<run_id>.spine.jsonl` 唯一;`SpineSink` 唯一写;`SpineReader` 唯一读;删 `events.jsonl` legacy;删 journal sink |
| **新增** | `lca_kernel/events/reader.py`(`SpineReader`);`lca_kernel/events/sinks/__init__.py`(`SinkBackend` Protocol + `SpineSink`);`lca_kernel/events/sinks/spine_file_sink.py` 改造(走 `SpineSink` 同接口) |
| **修改** | `lca/infrastructure/observability/spine/event_spine.py`:`append` 改走 `SpineSink.append`;`lca/infrastructure/observability/loop_cursor/coordinator_adapter.py`:`CoordAdapter.append` 改走 `SpineSink` |
| **删除** | `lca/plugins/events/sinks/journal/` 整个目录;`events.jsonl` reader;`lca/plugins/events/sinks/spine_file_sink/`(并入 `lca_kernel/events/sinks/spine_file_sink.py`) |
| **架构测试** | `test_i_fw_ssot_1`;`test_no_dual_sink` 仍通过 |
| **验收** | `rg "events\.jsonl" lca/ lca_kernel/` = 0;`rg "sinks.journal" lca/` = 0;`test_no_dual_sink` 通过 |
| **落地 commit** | `0e71f6bb`(骨架,含 PR-1+2+3+4) |

#### PR-5 record 单一入口

| 项 | 内容 |
|---|---|
| **目标** | `spine_runtime.build_record()` 单一 record 构造入口;`spine_file_sink` 删 `_build_event_record` 与 2 处 `except ValueError` enum fallback |
| **新增** | `lca_kernel/events/spine_runtime.py` 中 `build_record(payload, ref, *, chain=None)` 函数 |
| **修改** | `lca/plugins/events/sinks/spine_chain_sink/sink.py` 与 `spine_file_sink/sink.py` 改调 `build_record` |
| **删除** | `SpineFileSink._build_event_record`;两处 `except ValueError` 静默 fallback |
| **架构测试** | `tests/architecture/test_spine_record_single_builder.py` —— `lca/plugins/events/sinks/*/sink.py` 内无 `Channel(` / `Outcome(` 字面构造,无 `except ValueError` 后接 enum fallback |
| **验收** | `rg "_build_event_record" lca/` = 0;`rg "except ValueError" lca/plugins/events/sinks/` = 0 |
| **落地 commit** | `ff907239` |

#### PR-6 yaml 前缀规则 + 死配置清理

| 项 | 内容 |
|---|---|
| **目标** | `consumer_rules:` 前缀规则替代 `subscribers:` 逐 category 列举;删 `default_subscribers:` 死配置 |
| **新增** | `lca_kernel/events/config_parser.py`(`consumer_rules` 解析 + 求并) |
| **修改** | `lca_kernel/events/registry.py`:`can_consume` 改为 `can_consume(plugin, category) ∨ ∃rule: category.startswith(rule.prefix) ∧ plugin ∈ rule.plugins` |
| **删除** | `spine.yaml` 中 100 处 `subscribers:` 块 + 100 处 `default_subscribers:` 块;`team.yaml` 同上 |
| **架构测试** | `scripts/verify_consumer_rules_equivalence.py` —— 逐 category 比对前后授权集合全等 |
| **验收** | 等价性脚本 exit 0;`grep -c "subscribers:" spine.yaml` = 0;`grep -c "default_subscribers:" spine.yaml` = 0;`rg "default_subscribers" lca/ lca_kernel/ tests/` = 0(允许 `archive/` 与 `tests/architecture/test_*.py` 内的负向断言) |
| **落地 commit** | `f8032be0` |

#### PR-7 SinkBackend 协议 + Profile 装配 Pipeline

| 项 | 内容 |
|---|---|
| **目标** | `SinkBackend` Protocol 落地;`SpineSink` 默认实现;Profile YAML 装载 `pipeline:` 段;旧 `EventMechanism` 删除 |
| **新增** | `lca_kernel/events/sinks/spine_sink.py`(`SpineSink` 默认实现);`lca/harness/profile/pipeline_loader.py`(装载 `pipeline:` 段);`lca/profiles/event-pipeline/web-standard.yaml`(完整 Pipeline YAML,见 §3.3) |
| **修改** | `lca/harness/profile/boot.py`:Profile 启动时调 `bus.register_pipeline(pipeline)` |
| **删除** | `lca_kernel/events/mechanism.py`(整个文件);`lca_kernel/events/config/observability/spine.yaml`(替换为精简版,只剩 `events:` 段);旧 `subscribers:` 字段 |
| **架构测试** | `test_i_fw_ssot_1` 仍通过;`lca-ops inspect-pipeline <profile>` 输出 4 段(hooks/sinks/consumer_rules/options) |
| **验收** | `rg "EventMechanism" lca/ lca_kernel/ tests/` = 0(允许 `archive/` 与 `tests/architecture/test_*.py` 负向断言);`lca-ops inspect-pipeline web-standard` exit 0 |
| **落地 commit** | `1b8ce7a8`(PR-1+2+7+8+12 集成补漏) |

#### PR-8 reducer 收口

| 项 | 内容 |
|---|---|
| **目标** | `_instrument_apply` 改 `bus.publish`;删 16 处 `coord.emit_phase` 残留注释/兼容路径;reducer.apply_* 入口加 Protocol 约束 |
| **新增** | `lca/runtime/reducer.py` 重构:装饰器内调 `bus.publish` |
| **修改** | 16 处 `coord.emit_phase` / `CoordinatorAdapter.emit_phase` 删除(已 raise NotImplementedError,删方法即可);`lca/cognition/` `coord.begin_step` / `coord.record_*` 业务调用方迁 cursor |
| **删除** | `CoordinatorAdapter.emit_phase` 方法;16 处注释引用 |
| **架构测试** | `rg "coord\.emit_phase\|coord\.begin_step\|coord\.record_" lca/cognition lca/body lca/runtime lca/agent` = 0(已实测:5 处仅余 archive/注释) |
| **验收** | `lca-ops runs create --user-text "..."` 端到端通过;reducer.apply_* 全部走 bus.publish;`tests/runtime/test_reducer.py::test_instrument_apply_*` 通过 |
| **落地 commit** | `1b8ce7a8`(PR-1+2+7+8+12 集成补漏) |

#### PR-9 cursor 收口

| 项 | 内容 |
|---|---|
| **目标** | `coordinator_adapter.append` / `bind.append` / `event_spine.append` 合并为单一 spine port;cursor 走 `bus.publish` 而非直调 `SpineSink` |
| **新增** | `lca/infrastructure/observability/loop_cursor/_spine_port.py` 重构为 `_spine_port.bus_publish(payload, *, producer=CursorPlugin)` 单入口 |
| **修改** | `Cursor.record_*` 与 `CoordinatorAdapter.append` 全部走 `_spine_port.bus_publish` |
| **删除** | `event_spine.py:60 append`(`append` 走 `_spine_port`);`bind.py:80 append`(同上) |
| **架构测试** | `rg "def append" lca/infrastructure/observability/spine/event_spine.py lca/infrastructure/observability/loop_cursor/bind.py` = 0;`_spine_port.py` 唯一 append 实现 |
| **验收** | `_spine_port.py` 唯一 append;cursor step 写入正常;`tests/integration/test_loop_cursor_wiring.py` 通过 |
| **落地 commit** | `477c8a35` |

#### PR-10 runtime_loop 收口

| 项 | 内容 |
|---|---|
| **目标** | runtime_loop 4 键裸 dict → `EnvelopeEmitter.emit_exception_caught(record)`;`emit_phase` 16 处迁移到 `bus.publish` |
| **新增** | `lca/contracts/observability/exception_capture.py` 已存在(`ExceptionRecord`);`lca/runtime/runtime_loop.py` 重构 |
| **修改** | `lca/runtime/runtime_loop.py:281,296` 改为构造 `ExceptionRecord(boundary, exc_type, message, traceback_text, trace_id)` 调 `envelope_emit.emit_exception_caught(record)` |
| **删除** | 4 键裸 dict 调用 |
| **架构测试** | `rg "emit_exception_caught\(boundary\s*=" lca/` = 0;`rg "emit_exception_caught\(record" lca/` ≥ 1 |
| **验收** | `tests/runtime/test_runtime_loop_exception_path.py` 通过;integration run 触发异常后 `<run_id>.spine.jsonl` 含 `spine.exception.caught` event |
| **落地 commit** | `b84e750b` |

#### PR-11 状态机收敛

| 项 | 内容 |
|---|---|
| **目标** | `RunLifecycleStatus` 单 enum;删 `RunStatus` + `JournalRunStatus`;`_map_finish_status` + `journal_to_session_status` 映射表删除 |
| **新增** | `lca/contracts/observability/status.py`(`RunLifecycleStatus` 定义) |
| **修改** | `lca/infrastructure/observability/journal/engine/reducer.py`:`RunStatus` 改为 `RunLifecycleStatus` 别名(`RunStatus = RunLifecycleStatus`);`lca/plugins/transport/webserver/handlers/runs/terminal/status.py`:`JournalRunStatus` 同样改别名;`journal_to_session_status` 改为 identity;webserver session `status` 字段类型同步 |
| **删除** | `_map_finish_status` 函数;`journal_to_session_status` 映射表;`lca/infrastructure/observability/journal/engine/reducer.py:RunStatus` 类定义 |
| **架构测试** | `test_i_fw_ssot_2`;`rg "class RunStatus\b" lca/` = 0;`rg "class JournalRunStatus\b" lca/` = 0 |
| **验收** | 39 处 `RunStatus.` 引用全部走 `RunLifecycleStatus`;`_instrument_apply` 装饰器中 `outcome` 字符串 → `RunLifecycleStatus` 枚举;webstandard run 状态切换正常 |
| **落地 commit** | `84a3f946` |

#### PR-12 trace_id + 自观察

| 项 | 内容 |
|---|---|
| **目标** | contextvars 注入 trace_id;`event.bus.dispatch.{sinks,consumers}.end` 自指派观察事件;webserver lifespan adapter 跨请求隔离 |
| **新增** | `lca_kernel/events/hooks.py`:`TraceContextHook`(pre_dispatch,注入 trace_id);`MechanismDispatchObserver`(post_dispatch,自观察);`lca_kernel/events/payloads.py`:`MechanismDispatchEventPayload` |
| **修改** | `lca/plugins/transport/webserver/lifespan_adapter.py`:request 进入时 `_current_trace_id.set(uuid4)`,离开 reset;`lca_kernel/events/bus.py`:`send` 优先用 payload.trace_id → contextvars → new_id |
| **删除** | 21 个 publisher 直接传 `trace_id=""` 兼容路径(改为由机制注入) |
| **架构测试** | `tests/integration/test_webserver_trace_isolation.py`(并发请求 trace_id 不串);`rg "trace_id=[\"']" lca/plugins/events/publishers/` = 0 |
| **验收** | webserver run 1 + run 2 链上 trace_id 不串;机制自观察事件 `event.bus.dispatch.consumers.end` 在 spine.jsonl 中可见;Pipeline consumer_rules 不订阅 event.bus.dispatch.*(I-FW-BUS-4) |
| **落地 commit** | `1b8ce7a8`(PR-1+2+7+8+12 集成补漏) |

### 5.3 PR 顺序约束(理由)

| 顺序 | 理由 |
|---|---|
| PR-1 → PR-2 → PR-3 | 新机制壳 → hook 编排 → 类型化 schema;后 PR 依赖类型化做 hook payload |
| PR-3 → PR-4 | 单 SSOT 链依赖类型化 schema |
| PR-4 → PR-5 → PR-6 → PR-7 | 落盘链 → record 入口 → yaml 简化 → Pipeline 装载 |
| PR-7 → PR-8/9/10 | producer 端(PR-8/9/10)依赖 EventBus 替换 EventMechanism |
| PR-8/9/10 → PR-11 | 状态机收口在 producer 端迁移后做,避免遗漏 |
| PR-11 → PR-12 | trace_id 与自观察最后做,需全部 producer 走 bus.publish 后才有完整流量 |

**PR-1 合并前冻结新功能,只允许本框架 PR 通过**(临时 commit freeze,加 release note 标注)。

## 6. 与现有 ADR 的关系

| 现有 | 处置 |
|---|---|
| ADR-0167 spine SSOT | **吸收**:与新 SSOT 链合并;新 ADR § 3.5 重写 spine 部分 |
| ADR-0170 writable matrix | **不动**(独立范围);PR-7 装载时 `spine.writable.*` prefix 规则落到 Pipeline |
| ADR-0172 observability exporters | **吸收**:exporter 改为 `ExporterHook`(PostDispatchHook);`span_kind` 字段保留接入点但本 ADR 不实装 |
| ADR-0175 prompt trace | **不动**;`ModelVisibleHook` 在 PR-2 默认实现 |
| ADR-0176 step-tree deriver closure | **吸收**:deriver 改为 `SpineReader` 上的派生函数(§ 3.8) |
| ADR-0177 EnvelopeEmitter binding | **吸收**:Protocol 升级为 `EventBus[T]` + 4 hook Protocol;record 字段对齐 |
| ADR-0178 4 级收敛 | **吸收**:L1/L2/L3/L4 全部并入新框架;新增不变量 I-FW-BUS-1~4 取代 |
| ADR-0180 / 0181 event mechanism | **吸收**:EventMechanism → EventBus;22 个 manifest + 16 处遗留全迁(PR-1/8/9) |
| ADR-0182 EventMechanism 框架化 | **吸收**:D1(单入口) → `subscribe(*, failure=...)`;D6(record 单一入口) → PR-5;D7(yaml 前缀) → PR-6;D8(死插件) → PR-4;**不吸收**:D2(`FieldType` 字段类型化延后到 PR-3,本 ADR 仅 `FieldType` enum + 字符串字段);D3(自指派) → PR-12 用 hook 协议承担 |

**结论**:**10 篇现有 ADR 全部吸收**,本 ADR 是单一「事件总线框架 + 单 SSOT + 声明式编排」。

**新增吸收**:
- ADR-0169 D11(CoordinatorAdapter 收尾债)→ PR-8 收口
- ADR-0166 S5(异常路径走 exception.finally)→ 保留,新增 I-FW-BUS-1 守护

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 12 PR 合并周期长,中途分支漂移 | 每个 PR 独立可 revert;PR-1 后冻结新功能,只允许本框架 PR;`lca-ops` 提供 `lca-bus-status` 看每个 PR 落地状态 |
| Pipeline YAML 被滥用成平行机制 | I-FW-BUS-3 守护;Pipeline 不允许 import EventBus 内部,只能通过 Pipeline API |
| SinkBackend 实现漂移导致 SSOT 违反 | `SpineSink.to_dict()` 是 SSOT;任何 `RemoteSpineSink` / 其它后端必须实现同一接口 + 同一字节布局 |
| 单 SSOT 链损坏导致 run 全失 | `SpineSink` 启动时 checksum 校验;`SpineReader` 跳过损坏行;保留 `<run_id>.spine.jsonl.bak` 滚动备份 |
| 状态机三套并存的部分已合并,误删干净代码 | PR-11 前先 `rg "RunStatus\|JournalRunStatus" lca/contracts/`;若只剩 1 处,PR-11 改为「补 lint」 |
| runtime_loop 16 处 `emit_phase` 行为微差 | PR-10 前先 grep 每个调用点的当前行为列清单;迁移后跑集成测试对比 |
| reducer 装饰器被删后旧测试夹具不兼容 | PR-8 提供 `_instrument_apply` → `_bus_publish` 兼容装饰器;行为等价;14 天内零调用方再删 |
| cursor `record_*` 与 `bus.publish` 双写 | PR-9 一次性合并;`record_*` 保留为 façade(返回 `bus.publish` 的 ref);不在 cursor 内部持有状态 |
| `_instrument_apply` 装饰器测试依赖 outcome 字符串 | PR-11 之前把测试断言改成 `RunLifecycleStatus` 枚举比较;行为不变 |
| journal sink 删除后 `business/team.yaml` 引用断裂 | PR-4 前删 `team.yaml` 中 `JournalSink` 引用 |

**回滚**:12 个 PR 各自独立 revert。PR-1 → PR-7 只动机制壳 + 落盘,回滚成本最低;PR-8 → PR-10 动 producer 端,回滚后旧路径恢复。

## 8. 试点判定(每个 PR 合并前必答)

### 8.1 PR-1 合并前

1. **publish 是 producer 唯一入口**:架构测试断言 reducer/cursor/runtime_loop 无直写 spine / 直调 sink;白名单仅 `lca_kernel/events/`
2. **subscribe 是 consumer 唯一入口**:9 个真调用方 + 21 个 publisher 都迁完;架构测试断言 `EventMechanism.subscribe` / `register_sink` = 0 引用(除 archive)
3. **死插件不再装载即抛**:架构测试遍历所有 `manifest.py`,对批量 subscribe 的 plugin 断言 category 集合 ⊆ yaml consumers 集合
4. **journal sink 已删除**:`rg "sinks.journal" lca/` = 0;`test_no_dual_sink` 通过

### 8.2 PR-2 合并前

5. **Pipeline 装载成功**:`lca-ops inspect-pipeline web-standard` 输出全部 hook(stub)
6. **hook 链无循环**:单元测试模拟自指派(PreDispatchHook 返回 SkipDispatch),不触发新 dispatch

### 8.3 PR-3 合并前

7. **类型化字段不破坏现有 payload**:跑 `tests/lca_kernel/events/` + 21 个 publisher 的现有测试,所有原发出去的 payload 通过 schema 校验(否则 yaml 字段类型写错了,必须先修 yaml 再合)

### 8.4 PR-4 合并前

8. **单 SSOT 链生效**:`test_no_dual_sink` 通过;`events.jsonl` legacy 0 reader
9. **SpineReader 还原事件流**:integration run 跑完,`SpineReader.events(run_id)` 还原所有 EP,与旧 reader 一致

### 8.5 PR-7 合并前

10. **SinkBackend 协议可替换**:实现 `RemoteSpineSink` 用 S3 后端,装载后 `bus.subscribe` 测试通过
11. **Pipeline YAML 完整**:`lca-ops inspect-pipeline web-standard` 输出 4 段(hooks/sinks/consumer_rules/options)

### 8.6 PR-11 合并前

12. **状态机三套并存的剩余情况已确认**:grep 全仓确认只剩本 ADR 列出的 39 处 + 5 处

### 8.7 PR-12 合并前

13. **trace_id 跨 HTTP 请求隔离**:并发测试两个请求 trace_id 不串
14. **自指派无循环**:手动构造 `event.bus.dispatch.consumers.end` 并 `publish`,应不触发新的 dispatch 事件
15. **业务不订阅 framework 自观察事件**:I-FW-BUS-4 守护测试通过

## 9. 落地工具(commands)

```sh
# 验证 Pipeline YAML 装载
uv run lca-ops inspect-pipeline web-standard

# 验证 events schema
uv run lca-ops validate-events web-standard

# 验证架构不变量
uv run pytest tests/architecture/test_event_bus_invariants.py -v

# 等价性脚本(PR-6)
uv run python scripts/verify_consumer_rules_equivalence.py

# 总览本框架 PR 落地状态
uv run lca-ops event-bus-status
```

## 10. 附录(独立文件)

附录 A:101 个 category → 新 namespace 重映射表 → `docs/notes/implemented/seam/2026-09-03-event-bus-101-mapping.md`

附录 B:12 PR 兼容性矩阵(每个 PR 的兼容窗口、delete-when、合并顺序) → `docs/notes/implemented/runbook/2026-09-03-event-bus-pr-matrix.md`

附录 C:Pipeline YAML 完整示例 + 4 hook 默认实现 → `docs/notes/implemented/contract/2026-09-03-event-bus-pipeline-spec.md`

## 11. 实施完毕记录（2026-09-03）

**已落地证据**：

- 3 个附录 note 已从 `proposed/` 转 `implemented/`：附录 A（101 category mapping）/ 附录 B（PR 兼容性矩阵）/ 附录 C（Pipeline YAML 规范）
- 架构不变量测试 `tests/architecture/test_event_bus_invariants.py` **8 passed, 0 xfailed**：
  - I-FW-BUS-1（producer 唯一入口）：3 测试（含 cursor 走 WritePort facade 的 strict 守护）
  - I-FW-BUS-2（consumer 唯一入口）：1 测试（框架外 `.subscribe(` / `.register_sink(` 全收口）
  - I-FW-BUS-4（业务不订阅 dispatch 事件）：1 测试
  - I-FW-SSOT-1（`<run_id>.spine.jsonl` 唯一 SSOT）：3 测试（含 legacy reader 收口的 strict 守护）
- `scripts/event_bus_status.py` 输出：`ssot1-events-jsonl-legacy ok 0/0` + `pr5-new-build-record ok 6` + `eventbus-skeleton-modules ok True` + `pipeline-mount-points ok 16`
- `scripts/verify_consumer_rules_equivalence.py`：101 specs 全等(PR-6 收口验证)
- `rg "events\.jsonl" lca/ lca_kernel/ profiles/ bundles/` = **0**
- `rg "EventMechanism" lca/ lca_kernel/ tests/` = **20**(全部 `EventMechanismError` 类名 + 历史 docstring,无 module import / 类实例化)
- `EventBus.default().publish()` 调用方 = **17 个文件**(15 publisher plugin + reducer 装饰器 + 1 个 runtime 相关)
- `lca_kernel/events/mechanism.py` 已删除(commit `cfe4ad37`)
- `default_subscribers` 全仓 = 0；`coord.emit_phase` 实调用 = 0（剩 8 处全在历史叙事注释）；`class RunStatus\b` = 0；`class JournalRunStatus\b` = 0；`_map_finish_status` 实调用 = 0；`journal_to_session_status` 实调用 = 0；publisher `trace_id=""` = 0
