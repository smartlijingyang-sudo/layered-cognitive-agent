# Agent Note: ADR-0183 附录 C — Pipeline YAML 规范与 4 hook 默认实现契约

Status: proposed

## Problem

ADR-0183 §3.2(4 个 hook Protocol)、§3.3(Pipeline YAML 示例)、§3.4(SinkBackend 协议)是 Profile 作者与 plugin 作者的契约面。ADR 示例中的类路径、字段结构与实际代码存在未落地间隙,直接照抄会装不上。本附录把三段契约落成 contract note:完整 YAML 示例、Protocol 签名、默认实现清单逐项对照 PR-1~PR-4 已落地的代码,类路径以实际模块为准,未落地项显式标注决策点。

类路径基线(2026-09-03 实测):

- **已落地**:`lca_kernel/events/{bus,hooks,pipeline,registry,reader,spine_runtime,payloads,payloads_spine,errors}.py`、`lca_kernel/events/sinks/{__init__,spine_sink}.py`
- **ADR 给出路径但未落地**:`lca.plugins.observability.hooks.ModelVisibleHook`、`lca.plugins.observability.exporters.langfuse.LangfuseExporterHook`、`lca.plugins.events.sinks.remote_replicator.RemoteReplicatorSink`、`lca/harness/profile/pipeline_loader.py`(决策点均见各表)

## Decision

### C.1 Pipeline YAML 目标形态(ADR §3.3 完整示例)

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

示例中的类路径状态:已落地与未落地逐项见 C.4 / C.5;骨架解析器对示例结构的支持边界见 C.2。`spine.llm.` / `spine.exception.` / `spine.writable.` 的 fail_fast 归属与[附录 A](../seam/2026-09-03-event-bus-101-mapping.md) §A.4 一致。

### C.2 骨架解析器边界(`lca_kernel/events/pipeline.py`,PR-2 落地)

解析入口:`parse_pipeline_yaml(path: Path) -> Pipeline`;文件缺失返回空 `Pipeline`(Pipeline 装载为可选步骤)。

dataclass 结构:`Pipeline(name, version=1, hooks, sinks, consumer_rules)`;`HookSpec(id, hook, stage, config)`;`SinkSpec(id, backend, failure, config, depends_on)`;`ConsumerRule(prefix, plugins, failure)`;`Stage` 枚举 = {`pre_dispatch`, `post_dispatch`, `on_failure`}。

与 ADR §3.3 示例的差距:

| 项 | 骨架行为 | 差距 | 决策点 |
|---|---|---|---|
| `hooks[].id/hook/stage/config` | 解析;`stage` ∈ `Stage` | 一致 | — |
| `hooks[].enabled` | 不解析 | 示例无此字段,骨架亦无 | 按需,无排期承诺 |
| `sinks[].id/backend/failure/config` | 解析;`failure` ∈ `FailureSemantics` {`fail_fast`, `contained`} | 一致 | — |
| `sinks[].depends_on` | 解析为单个字符串 | 一致(示例亦为单字符串) | — |
| `consumer_rules[].prefix` | 解析 | 一致 | — |
| `consumer_rules[].consumers` | 读 `plugins:`(`consumers:` 为别名)作**扁平类路径列表**;failure 是**规则级**单值 | 示例为每 consumer 一个 `plugin:` + `failure:` 结构 | per-consumer failure 在 PR-7 定稿 |
| `options` 段 | 不解析 | 示例有 | PR-7 |
| `${from_env: X}` 占位符 | 不解析 | 示例的 langfuse hook 依赖 | PR-7;密钥只经 Profile `from_env` 进入(根 AGENTS.md §3) |

### C.3 4 个 hook Protocol(`lca_kernel/events/hooks.py`,已落地)

```python
class PreDispatchHook(Protocol):
    def before_publish(
        self,
        payload: EventPayload,
        producer: type,
        ctx: PublishContext,
    ) -> EventPayload | SkipDispatch: ...

class SpecResolverHook(Protocol):
    def resolve_spec(self, category: Category) -> EventSpec | None: ...

class PostDispatchHook(Protocol):
    def after_dispatch(
        self,
        payload: EventPayload,
        ref: EventRef,
        results: list[ConsumerResult],
    ) -> Iterable[EventPayload]: ...

class FailureHook(Protocol):
    def on_consumer_failure(
        self,
        payload: EventPayload,
        ref: EventRef,
        exc: BaseException,
    ) -> FailureAction: ...
```

辅助类型(同文件):

- `SkipDispatch`:哨兵。pre_dispatch 返回它表示跳过本事件。骨架 `EventBus._run_pre_dispatch` 收到时抛 `PayloadSchemaError`;ADR §3.2 的契约表述为静默跳过(不发、不落盘)。两种语义的对齐决策点 = PR-12。
- `FailureAction` = {`CONTAIN`(吞错,继续走 post_dispatch), `RETHROW`(上抛给 publish 调用方)}。
- `PublishContext(bus, producer, ts, trace_id=None)`:`trace_id` 注入留 stub,PR-12 启用 contextvars。
- `ConsumerResult(plugin, category, exc=None)`,`.failed` 属性。
- `EventRef` 定义在 `lca_kernel/events/mechanism.py`(hooks.py 经类型层引用);`EventPayload` / `Category` 在 `lca.contracts.event`。

### C.4 默认实现清单

| 类路径 | stage | 状态 | 行为 / 决策点 |
|---|---|---|---|
| `lca_kernel.events.hooks.TraceContextHook` | pre_dispatch | 已落地(stub:原样返回 payload) | PR-12 替换为 contextvars 注入 |
| `lca_kernel.events.hooks.PayloadSchemaHook` | pre_dispatch | 已落地(marker) | 实际校验由 `EventBus._validate_schema`(`bus.py`)执行 |
| `lca_kernel.events.hooks.DefaultFailureHook` | on_failure | 已落地 | 返回 `FailureAction.CONTAIN` |
| `lca_kernel.events.hooks.MechanismDispatchObserver` | post_dispatch | 已落地(stub:返回空 Iterable) | PR-12 yield `MechanismDispatchEventPayload` |
| `lca_kernel.events.payloads.MechanismDispatchEventPayload` | — | 已落地 | 自观察事件 payload;字符串闭集 `DISPATCH_SELF_OBSERVATION_CATEGORIES`,经 `EventBus._emit_self_observation` 内部路径流转 |
| `lca.plugins.observability.hooks.ModelVisibleHook` | pre_dispatch | 未落地(目录不存在) | ADR §3.3 示例引用;落地点随 model-visible 收口定 |
| `lca.plugins.observability.exporters.langfuse.LangfuseExporterHook` | post_dispatch | 未落地 | ADR-0172 吸收为 PostDispatchHook 形态 |
| `lca.plugins.events.sinks.remote_replicator.RemoteReplicatorSink` | sinks | 未落地 | ADR §3.3 可选镜像后端示例 |
| `SpecResolverHook` 默认实现 | — | 未定稿 | 类路径随 PR-3 yaml spec 装载一并定稿 |

### C.5 SinkBackend 与 SpineSink(`lca_kernel/events/sinks/`,已落地)

```python
# lca_kernel/events/sinks/__init__.py
class SinkBackend(Protocol):
    def append(self, record: SpineEventRecord) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
```

契约:`append` 的字节布局由 `record.to_dict()` 统一保证,backend 不可改字段名 / 字段顺序 / 序列化选项;`flush` 必须立即触发一次 fsync;`close` 后再 `append` / `flush` 必须 raise。

默认实现 `lca_kernel.events.sinks.spine_sink.SpineSink(SinkBackend)`:

- 构造参数:`path_template="{run_id}.spine.jsonl"`、`fsync_strategy="batch"`、`fsync_batch_size=100`、`fsync_interval_ms=50`、`checksum_on_open=True`
- 生命周期:`set_run_id(run_id)` 绑定 run_id 并打开 fd(重复调用 raise)→ `append` / `flush` → `close`(flush + close)
- `append` 写 `json.dumps(record.to_dict(), sort_keys=True) + "\n"`;close 后调用抛 `SpineSinkClosedError`
- fsync 节奏:`batch` 策略按条数或 `fsync_interval_ms` 阈值触发

字节布局 SSOT = `SpineEventRecord.to_dict()`(`lca_kernel/events/spine_runtime.py`),固定 9 字段:`event_id` / `category` / `execution_point` / `channel` / `payload` / `ts` / `causation_id` / `prev_event_hash` / `event_hash`(值可为 None,字段一律输出)。`from_dict` 是 `to_dict` 的逆,为 `SpineReader` 的唯一构造入口。ADR §3.5 的字段列举是设计期示意;实际字段以 `spine_runtime.py` 为准,字段调整走 ADR 流程。

读取入口 `lca_kernel/events.reader.SpineReader(run_id, *, path=None)`:`events()` 全量迭代、`filter(category_prefix=...)` 前缀过滤(I-FW-SSOT-1 唯一读盘者)。

### C.6 装配流程

`parse_pipeline_yaml(path)` → Profile 启动时调 `EventBus.register_pipeline(pipeline)`(`lca_kernel/events/bus.py`)一次,装载后不可热替换。

骨架 `register_pipeline` 只装载 hooks 段:按 `stage` 分桶到 `_pre_hooks` / `_post_hooks` / `_failure_hooks`,以 `before_publish` / `after_dispatch` / `on_consumer_failure` 的 hasattr duck-type 判别;实例化为零参 `spec.hook()`,`HookSpec.config` 已解析但实例化不传参——config 传参与 sinks / consumer_rules 段的装载决策点 = PR-7。

### C.7 相关不变量

| ID | 内容 |
|---|---|
| I-FW-BUS-3 | 自定义逻辑只能通过 Pipeline 编排 + 4 hook Protocol + SinkBackend 协议注入;plugin 不允许 import EventBus 内部 |
| I-FW-BUS-4 | 业务不订阅 `event.bus.dispatch.*`;`DISPATCH_SELF_OBSERVATION_CATEGORIES` 闭集 + `EventBus._emit_self_observation` 内部路径,架构测试守护 |
| I-FW-SSOT-1 | `<run_id>.spine.jsonl` 唯一事实链;`SpineSink` 唯一写、`SpineReader` 唯一读 |

## Alternatives considered

1. **YAML 内嵌 Python 代码(`exec`)** — 配置面获得任意代码执行能力,安全风险。**否决**。
2. **用 Python dataclass 字面量装载 Pipeline 而非 YAML** — Profile 无法声明式修改,Profile 作者必须写代码。**否决**。
3. **Hook 协议用 Callable 而非 Protocol** — 签名类型检查失效,plugin 漂移无守护。**否决**。
4. **Pipeline 用 DAG 而非线性 stage** — 复杂度增加,边际收益低;4 hook stage 已覆盖全部需求。**否决**。

## Acceptance criteria

- PR-7 合并后:`parse_pipeline_yaml` 解析 C.1 完整示例(含 per-consumer failure、options、`${from_env}`),`lca-ops inspect-pipeline web-standard` 输出与 C.1 结构一致
- 本附录标"已落地"的类路径全部可 import;标"未落地"的类路径在实现 PR 内同 PR 更新本附录
- `hooks.py` / `sinks/` 的契约变化(签名、构造参数、失败语义)必须同改本附录与对应测试

## Risks

1. **示例与解析器漂移** — C.2 已实测 4 处差距。**缓解**:PR-7 同 PR 更新 C.2 差距表;`lca-ops inspect-pipeline` 机械核对。
2. **hook 装载为 duck-type(hasattr)**,缺方法的 hook 静默跳过装载。**缓解**:PR-7 加 Pipeline 装载测试断言 hook 数量;Protocol 签名由 mypy 守护。
3. **`${from_env}` 解析缺失时静默成空串** — 凭证配置错误不可见。**缓解**:PR-7 实装时 env 缺失 raise `PipelineConfigError`。

## delete-when

- 12 PR 全部合并、C.1 示例可被完整装载且 C.2 差距表清空:本附录迁 `implemented/contract/`,按实施后状态改写
- Pipeline 契约被代码 docstring 与 `lca-ops inspect-pipeline` 输出完整承载后:本附录转 `archived/`
