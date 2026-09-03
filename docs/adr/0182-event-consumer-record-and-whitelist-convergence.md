# ADR-0182 — EventMechanism 框架化：消费入口收口 + 框架契约补齐

## 状态

Proposed（2026-09-03 起草；同日两次重写：第一次撤回 5 槽位分类法并把范围缩到
「record 单一入口 + yaml 前缀规则」；本次把方向翻转为「把 EventMechanism 收成
框架级契约」，覆盖消费入口合并、类型化注册表、自指派观察、trace 关联接入点，
并把之前两次发现的死插件与死配置一并清掉）。

## 背景

ADR-0180 / 0181 把事件机制做成 kernel 元层插件 `EventMechanism`。当前形态
（实测）：

| 项 | 实测值 |
|---|---|
| 公开方法 | `default` / `set_default` / `reset_singleton` / `send` / `subscribe` / `register_sink` / `validate_auth_matrix` / `registry` |
| `send` 调用方 | **21** 处 |
| `EventMechanism.subscribe` 真调用方 | **9** 个文件（3 manifest + 6 测试文件） |
| **`EventMechanism.register_sink` 真调用方** | **1**（`tests/plugins/events/sinks/test_spine_chain_sink.py` 单元测试；生产代码 0） |
| publishers 插件目录 | **16** 个 |
| subscribers / sinks 插件目录 | **5** 个 |
| 配置文件 | `lca_kernel/events/config/{observability,business,}/**/*.yaml` |
| 注册 category | 101（`spine.*` 100） |
| `spine.yaml` 行数 | 1614 |

机制已是完整形态，但**契约层和代码层都未对齐为框架**：

1. **入口语义裂**：ADR-0180 D4 承诺公开面只有 `send` + `subscribe`；ADR-0181
   D6 又加 `register_sink` 区分 FD-1（sink fail-fast）与 FD-2（subscriber
   contained）。结果是三个入口并存，**没有强制约束哪个该走哪个**。9 个
   `EventMechanism.subscribe` 真调用方中包括 3 个 sink manifest（journal /
   spine_file_sink / spine_chain_sink）——sink 全部错走 subscriber 入口，
   实际全在 FD-2 contained 路径运行。`EventMechanism.register_sink` 在生产
   代码 0 调用方（仅 1 个单元测试）。ADR-0181 D6 的 FD-1 语义在文档里有、
   在代码里没有。
2. **两个 sink plugin 装载即抛**（P0 运行时缺陷）：`SpineFileSink` 在
   `spine.yaml` 授权 **0/100** category，`JournalSink` 仅 **1/101**；两者
   manifest 仍对全量 category 批量 `subscribe`，触发
   `UnauthorizedSubscribeError`。不在任何 profile（`rg "event.sink.spine_file|
   event.sink.journal" profiles/ bundles/` = 0），所以生产未炸——是**装载即
   失败的死插件**。
3. **`spine_file_sink` 反推 record 含 silent fallback**：`sink.py:71-77` 两处
   `except ValueError` 把无法解析的枚举记为 `Channel.FACT` / `Outcome.SUCCESS`。
   第二处把失败记成成功，是可观测性真值的错误。
4. **`journal` sink 自带同名 `EventRecord` dataclass**（`sinks/journal/sink.py:17`），
   与 `lca/infrastructure/observability/spine/event_record.py:23` 同名异形，
   字段漂移的活标本。该 sink manifest 自称「后续 PR 接 BoundObservability.journal
   真正写盘」——无期限占位符。
5. **白名单逐 category 列举**：`subscribers:` 键 100 处，
   `default_subscribers:` 键 100 处（占 300 行）。新增全局 sink 必须改 100 处
   ——正是问题 2 的成因（PR-8 作者没改那 100 处）。
6. **`default_subscribers` 死配置**：全仓 `rg "\.default_subscribers"` 在
   `lca/` + `lca_kernel/` + tests/ 中**仅 1 处读者**（测试断言子集关系），
   fanout 实际只用运行时 `subscribe()` 注册的回调
   （`mechanism.py:223`）。
7. **`EventSpec.fields: dict[str, str]` 字符串字典**：`registry.py:34` 把字段
   类型记成 `str`，publisher 发错类型直到 chain 落盘后才发现。
8. **`EventRef.trace_id` 全是空字符串**（`mechanism.py:122`），机制对 trace
   没承诺。Langfuse / OTel exporter 是 spine 透传的另一个 trace_id 体系，**两
   条 trace 并存**。
9. **机制自指派观察缺失**：dispatch 抛错 / 吞错全在 `_log.exception` 里
   （`mechanism.py:227`），没有事件流量画像。

ADR-0181 PR-8 暴露了问题 2 的真实代价：plugin 类没进 yaml 授权，**框架本身
没阻止不一致**。本次重写把方向从「补 5 槽位」翻转为「把 EventMechanism 收成
产品级框架」。

## 目标

按严重度把 EventMechanism 收成 **框架级契约**，新增 4 类消费者 / 生产者**零成本
接入**：

| 目标 | 现状差距 |
|---|---|
| 框架公开面 = `send` + `register_consumer`（双入口；失败语义是参数不是入口） | 3 入口并存，FD-1 在代码里无人走 |
| 注册表 = 类型化 schema；yaml 解析错误 fail-fast | `fields: dict[str,str]`、未解析类别静默通过 |
| 机制自带 dispatch 观察事件 | 仅结构化日志 |
| trace_id 由机制注入，业务方不传 | 字段为空；两套 trace 并存 |

**不在范围**（独立 ADR 再开）：

- consumer 生命周期扩展（unregister / replace / version）：当前唯一注册来源是
  plugin boot，**没有第二个来源驱动这个 API**，按 C6 最小化先不做。
- `EventRef.dispatch_durations` 之外的延迟画像：等事件流量稳定再加。
- spine 自身的 trace_id 与 Langfuse exporter trace_id 的**语义统一**：这是
  ADR-0172 exporter 体系的范围，本 ADR 只预留 `EventSpec.span_kind` 接入点。

## 关键决策

### D1. 消费入口收敛为 `register_consumer(*, failure=...)`

```python
# lca_kernel/events/mechanism.py
class FailureSemantics(str, Enum):
    FAIL_FAST = "fail_fast"    # 落盘型：首个 callback 抛错上抛 sender（FD-1）
    CONTAINED = "contained"    # 派生型：抛错被吞，原事件继续（FD-2）

def register_consumer(
    self,
    *,
    plugin: type,
    category: Category,
    callback: ConsumerCallback,
    failure: FailureSemantics = FailureSemantics.CONTAINED,
) -> None:
    """框架唯一的消费方注册入口。

    ``plugin`` 必须是 Python class；机制按 yaml consumers 解析后的 type 鉴权。
    ``failure`` 决定 dispatch 行为，机制按值选路径——调用方不需选入口。
    """
    if plugin is None or not isinstance(plugin, type):
        raise MissingPluginIdentityError("register_consumer")
    if not self._registry.can_consume(plugin, category):
        raise UnauthorizedConsumeError(plugin.__qualname__, category.value)
    if failure is FailureSemantics.FAIL_FAST:
        self._sinks[category].append((plugin, callback))
    else:
        self._consumers[category].append((plugin, callback))
```

`send()` 内部分流保持：

```python
self._dispatch_sinks(payload, ref)          # FAIL_FAST，抛错上抛
self._dispatch_consumers(payload, ref)       # CONTAINED，except Exception 吞
```

**删除**：`subscribe` / `register_sink` 两个入口（ADR-0180 D4 + ADR-0181 D6
双吸收）；改名为 `register_consumer` 后对外暴露 2 个入口（`send` + `register_consumer`），
对内用 `_sinks` / `_consumers` 两份字典分流。

**yaml 升级**：

```yaml
# lca_kernel/events/config/observability/spine.yaml
events:
  - category: spine.cognition.brain.perceive.start
    plane: lca.contracts.event.Plane.OBSERVABILITY
    payload_class: lca_kernel.events.payloads_spine.SpineEventPayload
    fields:
      state_id: str
    publishers:
      - lca.plugins.events.publishers.spine_reflector_cognition.plugin.ReflectorClass
    consumers:                              # 新增：取代 subscribers + default_subscribers
      - plugin: lca.plugins.events.sinks.spine_chain_sink.sink.SpineChainSink
        failure: fail_fast
      - plugin: lca.plugins.events.subscribers.console_projector.subscriber.ConsoleProjectorSubscriber
        failure: contained
```

| 字段 | 类型 | 校验 |
|---|---|---|
| `plugin` | class 全路径 | `importlib` 解析为 `type`，沿用 ADR-0180 D2 |
| `failure` | enum（`fail_fast` / `contained`） | 必须可解析为 `FailureSemantics`，否则 `UnknownFailureSemanticsError` |

**类型一致性保护**：注册时若 `failure` 与 yaml `consumers:` 中声明不一致，
抛 `FailureSemanticsMismatchError`（防止「代码写 contained 但 yaml 写
fail_fast」这种半迁移态）。

**不引入 `Slot` enum / `SinkSlot` Protocol / `sink_slot.py` 模块**：分类学不
产生约束力（D2 撤回稿已论述），失败语义已经在 `FailureSemantics` 里编码。

**不引入 `slot_bindings` fallback 双写**：原 PR 风险缓解的「`slot_bindings` 缺
失则 fallback 旧字段」违反 AGENTS.md §1 兼容模板——yaml 一次性等价迁移，跑脚
本证明授权集合全等。

**架构测试** `tests/architecture/test_mechanism_single_consumer_entry.py`：
- `lca_kernel/events/mechanism.py` 内**无** `def subscribe` / `def register_sink`
- `lca/` + `lca_kernel/` + `tests/` 内**无** `\.subscribe(` / `\.register_sink(`
  调用（除 `archive/` 与版本注释）
- yaml 每个 category 必须有 `consumers:` 字段，且每个 consumer 必带 `failure`

**新引入不变量 I-FW-1**：消费方注册只能走 `register_consumer(*, failure=...)`，
失败语义是参数不是入口。

### D2. 类型化 `EventSpec.fields`

```python
# lca_kernel/events/registry.py
class FieldType(str, Enum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    JSON = "json"      # 嵌套 dict / list
    EVENT_REF = "event_ref"   # 引用另一条事件

@dataclass(frozen=True)
class EventSpec:
    category: Category
    plane: Plane
    payload_class: type[EventPayload]
    fields: dict[str, FieldType] = field(default_factory=dict)
    consumers: tuple[ConsumerBinding, ...] = ()      # 替代 publishers/subscribers/default_subscribers
    span_kind: SpanKind | None = None                # D5 接入点

@dataclass(frozen=True)
class ConsumerBinding:
    plugin: type
    failure: FailureSemantics
```

**`send()` 加 payload schema 校验**：

```python
def send(self, payload: EventPayload, *, plugin: type) -> EventRef:
    ...
    spec = self._registry.spec_for(payload.category)
    if spec is not None:
        for fname, ftype in spec.fields.items():
            if ftype is FieldType.EVENT_REF:
                continue
            _validate_field(payload, fname, ftype)    # 类型不匹配 → PayloadSchemaError（FD-1 上抛 sender）
    ...
```

**不强制业务方用类型化 schema**——`fields` 为空（未知 category 或不声明字段）
时跳过校验。**只对已在 yaml 声明 `fields:` 的 category 强制**。

**架构测试**：枚举 5 个 yaml 中的 `fields:` 字段，每个都应是 `FieldType` enum 值。

### D3. 自指派观察：dispatch 发事件

机制把 dispatch 流量变成 EventMechanism 自己的事件，**框架观测自己的流量**：

```python
# lca_kernel/events/mechanism.py
def _dispatch_sinks(self, payload: EventPayload, ref: EventRef) -> None:
    dispatch_start = time.monotonic()
    failed_plugin: type | None = None
    try:
        for _plugin_cls, callback in self._sinks.get(payload.category, ()):
            callback(payload, ref)
    except Exception:
        failed_plugin = _plugin_cls
        raise
    finally:
        _emit_mechanism_dispatch_end(
            category=payload.category,
            stage="sinks",
            consumer_count=len(self._sinks.get(payload.category, ())),
            duration_s=time.monotonic() - dispatch_start,
            failed_plugin=failed_plugin.__qualname__ if failed_plugin else None,
        )

def _dispatch_consumers(self, payload: EventPayload, ref: EventRef) -> None:
    dispatch_start = time.monotonic()
    contained_failures: list[str] = []
    for _plugin_cls, callback in self._consumers.get(payload.category, ()):
        try:
            callback(payload, ref)
        except Exception:
            contained_failures.append(_plugin_cls.__qualname__)
            _log.exception(...)
    _emit_mechanism_dispatch_end(
        category=payload.category,
        stage="consumers",
        consumer_count=len(self._consumers.get(payload.category, ())),
        duration_s=time.monotonic() - dispatch_start,
        contained_failures=tuple(contained_failures),
    )
```

新事件用最小 payload 形态（**不**走 `SpineEventPayload`——机制不属于 spine
命名空间）：

```python
# lca_kernel/events/mechanism_observer.py
class MechanismDispatchEventPayload:
    """机制自指派观察事件。
    不属于 spine.*；category = event.mechanism.dispatch.{sinks,consumers}.end
    """
    category: str
    consumer_count: int
    duration_s: float
    failed_plugin: str | None = None
    contained_failures: tuple[str, ...] = ()
```

**yaml 新增 2 个 category**：

```yaml
- category: event.mechanism.dispatch.sinks.end
  plane: lca.contracts.event.Plane.OBSERVABILITY
  payload_class: lca_kernel.events.mechanism_observer.MechanismDispatchEventPayload
  fields: {consumer_count: int, duration_s: float, failed_plugin: str}
  consumers: []   # 框架自观察，不允许业务订阅防止循环
- category: event.mechanism.dispatch.consumers.end
  payload_class: lca_kernel.events.mechanism_observer.MechanismDispatchEventPayload
  fields: {consumer_count: int, duration_s: float, contained_failures: json}
  consumers: []
```

**守护循环**：`send()` 内**不**触发 `send()`——`_emit_mechanism_dispatch_end`
直接写 `_consumers[event.mechanism.dispatch.consumers.end]` 路径，绕过
`send()` 的鉴权 + 再 dispatch。否则会无限自指派。

**新引入不变量 I-FW-2**：机制 dispatch 流量是 EventMechanism 自指派的事件；
业务方**不**订阅 `event.mechanism.dispatch.*`（yaml `consumers:` 留空 +
架构测试守护）。

### D4. trace_id 由机制从 `contextvars` 注入

```python
# lca_kernel/events/mechanism.py
import contextvars

_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lca_event_trace_id", default=None
)

def send(self, payload: EventPayload, *, plugin: type) -> EventRef:
    ...
    trace_id = payload.trace_id or _current_trace_id.get() or new_id("trc")
    ref = EventRef(
        event_id=new_id("evt"),
        category=category.value,
        trace_id=trace_id,
        ts=time.time(),
    )
    ...
```

**业务方不再传 `trace_id`**：

- `SpineEventPayload.trace_id` 字段保留为可读字段，机制优先用 `payload.trace_id`
  （兼容旧 publisher），缺则用 contextvar，再缺则新生成。
- `contextvars` 由 webserver lifespan adapter 在 HTTP request 进入时 set，
  离开时 reset（沿用 ADR-0179 上下文管理的 hook 点）。

**架构测试**：`spine_reflector_*` 21 处 publisher 不直接 set
`_current_trace_id`（不绕过机制）。

### D5. `EventSpec.span_kind` 作为 trace 接入点（仅占位，不实装）

```python
class SpanKind(str, Enum):
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"
```

```yaml
- category: spine.runtime.llm.call.start
  span_kind: producer           # 机制在 send 时给 OTel exporter 一个 hint
  ...
```

**当前不实装 OTel span 创建**，仅作为 D4 trace_id 注入之外的"未来框架扩展点"。
ADR-0172 之后用单独的 ADR 接 OTel；本 ADR 不绑死具体 exporter。

**不引入**：OTel / Langfuse SDK 依赖、具体 span 创建代码、trace 上下文传递
协议。这些都属 ADR-0172。

### D6. record 单一构造入口（继承前次决策）

```python
# lca_kernel/events/spine_runtime.py
def build_record(
    payload: EventPayload,
    ref: EventRef,
    *,
    chain: SpineChainContext | None = None,
) -> SpineEventRecord:
    """spine 落盘 plugin 的唯一 record 构造入口。

    失败语义：payload 非 SpineEventPayload → TypeError（不 fallback）。
    所有权：SpineEventRecord.to_dict() 是链上字节布局 SSOT。
    """
    if not is_spine_event(payload):
        raise TypeError(
            f"build_record 只接 SpineEventPayload；got {type(payload).__name__}"
        )
    return SpineEventRecord.build(payload, ref, chain=chain)
```

**新引入不变量 I-SINK-1**：spine 落盘 plugin 必须经 `build_record()` 构造
record；不得反推 `Channel` / `Outcome`，不得为枚举解析失败提供 fallback。

**架构测试** `tests/architecture/test_spine_record_single_builder.py`：
- `lca/plugins/events/sinks/*/sink.py` 内无 `Channel(` / `Outcome(` 字面构造
- `lca/plugins/events/sinks/*/sink.py` 内无 `except ValueError` 后接枚举 fallback

### D7. yaml 白名单改前缀规则

`spine.yaml` 顶层新增 `consumer_rules` 段；`EventSpec.consumers` 由
「本条 category 显式列表 ∪ 匹配的前缀规则」求并：

```yaml
consumer_rules:
  - prefix: "spine."
    consumers:
      - plugin: lca.plugins.events.sinks.spine_chain_sink.sink.SpineChainSink
        failure: fail_fast
      - plugin: lca.plugins.events.subscribers.console_projector.subscriber.ConsoleProjectorSubscriber
        failure: contained
      - plugin: lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber.SpineStepTreeAccumulator
        failure: contained

events:
  - category: spine.cognition.brain.perceive.start
    publishers:
      - lca.plugins.events.publishers.spine_reflector_cognition.plugin.ReflectorClass
    # consumers: 省略 —— 由 consumer_rules 的 "spine." 规则覆盖
```

`publishers` **保持逐 category 显式**：publisher 是"谁有权发这一条"，按条
授权是正确粒度。

**删 `subscribers:` + `default_subscribers:` 两个字段**（D1 已删 + D3 解决）。

**行数实测预期**：删 100 处 `subscribers:` 块（300 行）+ 100 处
`default_subscribers:` 块（300 行）+ 新增 ~12 行规则 ≈ **1614 → ~1020 行**
（PR-2 落地后以实测复核，不作验收门）。

**验收门（行为等价）**：

```sh
uv run python scripts/verify_consumer_rules_equivalence.py
```

逐 category 对比重构前后 `consumers` 集合全等。

### D8. 死插件与死配置处置

**`journal` sink → 删除整目录 + 2 处 yaml 引用**：

| 文件 | 行 | 动作 |
|---|---|---|
| `lca/plugins/events/sinks/journal/`（manifest.py + sink.py + __init__.py） | 39 + 11 | 删 |
| `lca_kernel/events/config/business/team.yaml:21,24` | 2 | 删 `JournalSink` 引用 |
| `lca_kernel/events/__init__.py:11` | docstring 提及 | 改 |

**注意**：`lca/cognition/perceive_sink.py:69` 有**另一个同名** `JournalSink`
（Hub 适配器，非 events 插件），不在删除范围。

**`spine_file_sink` → 保留 plugin，重写实现 + 补授权 + 接 profile**：

- 删 `_build_event_record()`，改走 D6 的 `build_record()`
- 删两处 `except ValueError` 枚举 fallback（`sink.py:71-77`）
- 该 plugin 类进 D7 的 `spine.` 前缀规则（`failure: fail_fast`）
- plugin id `lca.events.sink.spine_file` 进 `profiles/web-standard.yaml`

理由：`FileSink` 有真实非 shim 消费方
（`lca/infrastructure/observability/loop_cursor/persistence_coordinator.py:29`），
`<run_id>.spine.jsonl` 是 `lca-ops journal exceptions` 数据源，不能删。

**新引入不变量 I-FW-3**：批量 `register_consumer` 的 category 集合必须被 yaml
白名单完全覆盖；架构测试守护（防问题 2 重演）。

## 不变量承接

| 不变量 | 本 ADR 处理 |
|---|---|
| C1 闭集 | 不增循环步骤；机制不感知具体 plugin；新增 category 由 yaml 扩展 |
| C2 双平面 | 不动认知/世界边界；机制在 kernel 层 |
| C3 Journal | D6 使 `SpineEventRecord.to_dict()` 成为落盘字节布局唯一来源；D8 删掉无法承担 C3 的 journal 占位 sink |
| C4 Reducer | 不动 |
| C5 能力衰减 | D7 前缀规则不放宽授权（等价性脚本证明授权集合全等） |
| C6 最小化 | 净新增 = 1 个 `register_consumer` + `FailureSemantics` enum + `FieldType` enum + `ConsumerBinding` dataclass + `EventSpec.span_kind` 字段；不引 imperative 框架 / DAG / 槽位 enum / Slot protocol |
| C7 控制/观察分离 | D3 让机制自带观察事件；不动控制路径 |
| **新引入 I-FW-1** | 消费方注册只能走 `register_consumer(*, failure=...)` |
| **新引入 I-FW-2** | 业务方不订阅 `event.mechanism.dispatch.*` |
| **新引入 I-FW-3** | 批量 `register_consumer` 的 category 集合必须被 yaml 白名单完全覆盖 |
| **新引入 I-SINK-1** | spine 落盘 plugin 必须经 `build_record()` |

## 迁移 PR 切分

| PR | 内容 | 删-when / 验收 |
|---|---|---|
| **PR-1 record 单一入口** | `spine_runtime.build_record()`；`spine_chain_sink` / `spine_file_sink` 改调它；`spine_file_sink` 删 `_build_event_record()` 与两处枚举 fallback；架构测试 `test_spine_record_single_builder.py` | `rg "_build_event_record" lca/` = 0；`rg "except ValueError" lca/plugins/events/sinks/` = 0 |
| **PR-2 yaml 前缀规则** | `consumer_rules` 解析；`spine.yaml` 100 处 `subscribers:` 块删除；`scripts/verify_consumer_rules_equivalence.py` | 等价性脚本 exit 0；`grep -c "subscribers:" spine.yaml` = 0 |
| **PR-3 死配置删除** | `default_subscribers` 字段 + 100 处 yaml 块 + 测试断言 | `rg "default_subscribers" lca/ lca_kernel/ tests/` = 0 |
| **PR-4 死插件处置** | 删 `sinks/journal/` + `business/team.yaml` 2 处引用 + `events/__init__.py` docstring；`spine_file_sink` 进 `spine.` 前缀规则（`failure: fail_fast`）+ plugin id 进 `profiles/web-standard.yaml`；架构测试断言「批量 `register_consumer` 的 category 集合 ⊆ yaml `consumers` 集合」 | `rg "sinks.journal" lca/ lca_kernel/` = 0；`lca-ops inspect-tree web-standard` 含 `lca.events.sink.spine_file`；boot 不抛 `UnauthorizedConsumeError` |
| **PR-5 消费入口收敛** | `FailureSemantics` enum；`register_consumer(*, failure=...)` 替代 `subscribe` + `register_sink`；9 个 `subscribe` 真调用方 + 1 个 `register_sink` 单测迁移；yaml `consumers:` 替代 `subscribers:` + `default_subscribers:`；架构测试 `test_mechanism_single_consumer_entry.py`（白名单仅 `lca_kernel/events/`、`lca/plugins/events/`、`lca/harness/` 业务注册路径，不含 `live_tail` / `event_spine` / `bus` 等无关对象的 `subscribe`） | `grep "def subscribe\|def register_sink" lca_kernel/events/mechanism.py` = 0；架构测试断言 EventMechanism 的两个入口均无其它调用方；yaml `consumers:` 全覆盖 |
| **PR-6 注册表类型化** | `FieldType` enum；`EventSpec.fields: dict[str, FieldType]`；yaml 解析升级；`send()` payload schema 校验；`EventSpec.consumers: tuple[ConsumerBinding, ...]`；`ConsumerBinding` dataclass | `rg "fields.*dict\[str, str\]" lca_kernel/events/` = 0；payload 类型不匹配 → `PayloadSchemaError` |
| **PR-7 自指派观察** | `MechanismDispatchEventPayload`；2 个 `event.mechanism.dispatch.*.end` category；`_dispatch_sinks` / `_dispatch_consumers` 发事件；`lca-ops event-stats` 子命令 | `rg "_log\.exception" lca_kernel/events/mechanism.py` = 0（机制错误走事件）；`lca-ops event-stats <run_id>` 可输出 |
| **PR-8 trace_id 注入** | `contextvars` + `_current_trace_id`；`send()` 注入；webserver lifespan adapter 在 request 边界 set/reset | `rg "trace_id=[\"']" lca/plugins/events/publishers/` = 0（业务方不手填 trace_id） |

**顺序约束**：

```
PR-1 → PR-2 → PR-3 → PR-4 → PR-5 → PR-6 → PR-7 → PR-8
                └→ PR-5 依赖 PR-2/3/4 提供清晰的迁移基线
                              └→ PR-6 依赖 PR-5 的 ConsumerBinding
                                            └→ PR-7/8 在 PR-5 完成后并行
```

8 个 PR 全部独立可 revert。

**不在本 ADR 范围**：

- ADR-0181 PR-4~PR-10 遗留的 `_spine.append`（21 处）/ `coord.emit_phase`
  （16 处）收口——属 ADR-0181 执行债，本 ADR 只更正其计数，不接管。
- consumer 生命周期扩展（unregister / replace / version）：按分叉 A 决定
  暂缓，等第二个注册来源出现时再开 ADR。
- Langfuse / OTel SDK 接入、`EventSpec.span_kind` 实装：按分叉 B 决定暂缓，
  属 ADR-0172 后续。

## 试点"盖章"判定

PR-5 合并前必须回答：

1. **`register_consumer` 是唯一消费入口**：架构测试断言
   `mechanism.py` 无 `def subscribe` / `def register_sink`；`EventMechanism`
   类型对象上无 `.subscribe(` / `.register_sink(` 调用（白名单仅含
   `lca_kernel/events/mechanism.py` 内自身的旧引用与 `archive/` 注释）。
   `tail.subscribe` / `event_spine.subscribe` / `store.subscribe` /
   `bus.subscribe` 是不同对象，不在检查范围。
2. **失败语义参数化**：`register_consumer` 同时支持 `fail_fast` 与 `contained`，
   单元测试覆盖两条路径（fail_fast 抛错上抛、contained 抛错被吞且发
   `event.mechanism.dispatch.consumers.end`）。
3. **死插件不再产生**：架构测试遍历 `lca/plugins/events/**/manifest.py`，对
   每个批量 `register_consumer` 的 plugin 断言其 category 集合 ⊆ yaml `consumers`
   集合；当前 `SpineFileSink`（0/100）与 `JournalSink`（1/101）必须使该测试
   **先红**。
4. **`subscribe` / `register_sink` 真正无人调**：`rg "\.subscribe(\|\.register_sink("`
   仅命中 `lca_kernel/events/mechanism.py` 的删除注释或 `archive/`。

PR-6 合并前：

5. **类型化字段不破坏现有 payload**：跑 `tests/lca_kernel/events/` + 21 个 publisher
   的现有测试，所有原发出去的 payload 通过 schema 校验（否则 yaml 字段类型写
   错了，必须先修 yaml 再合）。

PR-7 合并前：

6. **自指派无循环**：手动构造 `event.mechanism.dispatch.consumers.end` 事件
   并 `send`，应**不**触发新的 `event.mechanism.dispatch.consumers.end`（直接
   走 `_consumers` 字典，不进 `send()`）。

PR-8 合并前：

7. **trace_id 跨 HTTP 请求隔离**：跑 `tests/integration/test_webserver_trace_*.py`
   （PR-8 新增），断言两个并发请求 trace_id 不串。

## 与现有 ADR 的关系

| 既有 | 处理 |
|---|---|
| ADR-0180 鉴权矩阵 / send-subscribe 公开面 | **吸收**：D1 把 D4「只有 send + subscribe」与 ADR-0181 D6「FD-1/FD-2」合并为 `register_consumer(*, failure=...)`，D4 字面更新为「send + register_consumer」 |
| ADR-0181 spine 降为 publishers/sinks/subscribers | **吸收**：PR-1~5 清掉 PR-8 遗留死插件与计数误差；D1 删除 `subscribe` / `register_sink` 入口（D6 失败语义由 `FailureSemantics` 字段保留） |
| ADR-0172 observability-exporters | **不绑定**：D5 `span_kind` 是接入点，D8 不实装 OTel SDK；后续 ADR 单独接 |
| ADR-0177 / 0170 / 0070 | **不取代、不吸收**，保持 Accepted |

**ADR-0180 D4 字面改动**（由本 ADR 落地时一并更新）：

```diff
- 公开面只暴露 ``send`` 与 ``subscribe`` 两个入口；其他全部 internal。
+ 公开面只暴露 ``send`` 与 ``register_consumer`` 两个入口；其他全部 internal。
+ 失败语义由 ``register_consumer(..., failure=...)`` 参数决定，
+ 不是入口区分（详见 ADR-0182 D1）。
```

## 风险与回滚

- **风险 1（PR-2 授权面漂移）**：前缀规则可能意外扩大 plugin 可订阅范围。
  **缓解**：验收 4 的等价性脚本逐 category 比对；不等价即不合。
- **风险 2（PR-4 删 journal sink 影响 team.yaml）**：`business/team.yaml` 2 处
  引用 `JournalSink`。**缓解**：跑 `tests/lca_kernel/events tests/plugins/events`
  + `tests/test_team_message_tool.py`（注意 `lca/cognition/perceive_sink.py:69`
  有另一个同名 `JournalSink`，不在删除范围）。
- **风险 3（PR-4 改 `spine_file_sink` 落盘路径）**：`<run_id>.spine.jsonl` 是
  `lca-ops journal exceptions` 数据源。**缓解**：保持 `FileSink` 磁盘字段
  不变，仅换 record 构造来源；跑 `tests/observability/spine/sinks/test_file_sink.py`
  + `tests/cli/test_journal_exceptions_command.py`。
- **风险 4（PR-5 yaml 改 schema 跨 100 category）**：解析失败静默通过 vs
  fail-fast。**缓解**：PR-5 不删旧 `subscribers:` 字段，**同时**新增
  `consumers:`；解析时若 `consumers:` 缺失 → 报错（不 fallback 到 `subscribers:`）；
  yaml 一次性等价迁移 + 等价性脚本。
- **风险 5（PR-6 payload schema 校验 false positive）**：现有 publisher 发
  的 payload 与 yaml 声明的字段类型不匹配。**缓解**：先用 `rg "fields:" spine.yaml`
  数字段类型，全量跑现有测试；若 yaml 写错类型，先修 yaml 再合。
- **风险 6（PR-7 自指派循环）**：`event.mechanism.dispatch.consumers.end`
  触发新 dispatch。**缓解**：`_emit_mechanism_dispatch_end` 直接写
  `_consumers[category]`，**不**调 `send()`；单元测试模拟自指派（验收 6）。
- **风险 7（PR-8 trace_id contextvar 跨异步任务污染）**：`contextvars` 在
  `asyncio.create_task` 内自动隔离；webserver lifespan adapter 在 request
  边界 set/reset。**缓解**：验收 7 的并发测试。
- **回滚**：8 个 PR 各自独立 revert。PR-2 / PR-3 / PR-5 只删死配置与改声明
  方式，回滚即恢复 yaml 原文与入口定义。
