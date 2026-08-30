# 日志系统评估 —— 职责边界 / 架构优雅 / 认知清晰 / 原语清晰

**评估日期**：2026-08-20
**评估对象**：`lca/layer0_infra/observability/` 全部模块 + 跨层日志发射点
**评估目的**：在合并 [`ADR-0063`](../../adr/0063-run-trace-ssot.md) 与 `refactor/run-diagnostics-plugin` 之前，沉淀当前日志系统的结构性问题清单，供后续 ADR 选题。

本文档**只列问题**，不列修复方案。每条问题指向具体文件 / 行号 / 模块,后续 ADR 评审时直接引用本文条目编号。

---

## 一、职责边界清晰度

### 1. 同一份事实在四套平行坐标系里被多重表达

| 概念 | 在哪里 | 命名/序列化 |
|---|---|---|
| 真源事件 | `RunStore._events` (list) | `StampedEvent` (frozen) |
| 进程级聚合 | `ProcessJournal` | 重新 mint seq 的 StampedEvent (`replace`) |
| Live 内存 | `LiveTail._frames` (deque) | StampedEvent |
| 落盘 | `JsonlJournalProjector` | jsonl record (`stamped_to_record`) |
| SSE 帧 | `stamped_to_sse_frame` | 同 record + event 字段 |

`RunStore.seq = log.length` 是 ADR-0055 N2 不变量;`ProcessJournal.publish` 又把 seq 重新 mint 一次,等于同一条事实携带两个 seq 坐标(`StampedEvent.seq` 与 `_BoundProcessJournal._seq`)。

### 2. `record()` 是"假装一行"的 super facade,底下是 9 步管线

`facade.record(event) → current_hub() → NullObject()/hub.store.append → _resolve_subscribers → 词表校验 → _validate_append_boundary(deepcopy + frozen 断言) → get_current_run_scope → _apply_policy → StampedEvent 构造 → 通知所有 _IsolatedSubscriber → 增量投影缓存失效`。每一行 `record()` 都走完全程,业务层不可见。

### 3. `LiveTail` 同时是四种身份

`gateway/runs/live.py:LiveTail` 同时实现:`JournalProjector` 协议(消费者)/ ring buffer(内存数据库)/ pub/sub broker(fan-out)/ replay source(in-mem replay)。`subscriber_count`/`evicted` 是诊断指标,但状态机 `_closed/_evicted/_last_seq` 与 `ObservabilityHub._released/_disposed` 是平行坐标系。

### 4. 同一概念被 4 个抽象层重复

`journal event → SSE bytes` 这一管道,至少有 4 个文件各自实现:

- `SSEJournalProjector` (协议实现,零翻译)
- `LiveTail` (in-mem ring + fan-out + replay)
- `iter_live_sse` (api.py 的 async generator + 心跳)
- `process_journal.py` (process-wide 重新 seq 后再 publish)

`SSEJournalProjector` 文档明说"留给其它入口/单测",主线从来没用过。

### 5. 两个 Sink 抽象重叠

`perceive_sink.py:ManifestSink` Protocol 有 3 个实现 `NullSink` / `RunStoreSink` / `JournalSink`;后者绕一圈调 `facade.record()`。`JournalSink.emit` 又读 `cognitive_loop_settings.context_manifest_dual_write` 这个 flag——同一事件可走两条路。

### 6. `ManifestSink` 的 "must be idempotent" 写进 docstring,实现非幂等

测试路径 `RunStore.append` 直接喂,生产路径 `JournalSink` 走 facade.record。两者不是幂等兼容的——RunStore 是 append-only 但每次生成新 seq,facade.record 又有隔离保护。一份"幂等语义"承诺,两种实现行为。

### 7. `ConsoleJournalProjector` 与 `FactStreamProjector` 70% 重复

两个 projector 都从 journal 读、都做事件分类(table-driven handler)、都维护角色切换的 section header、都做容器事件/叙事事件的分派。差异只有:`FactStreamProjector` 多 `_total_prompt_tokens` 等累计 + 多 `_step_group` 缩进。约 700 行重复渲染代码,且 verbosity 控制点不一致(console 用 `Verbosity` enum,fact 用 `verbose=True/False` 开关)。

### 8. `_IsolatedSubscriber` / `_IsolatedExporter` / `_safe_detach` 三处独立实现"失败只 log"

都是 `try/except + _log.warning("..._failed", ...)`,重复三次,没统一的 retry/silence 包装件。

### 9. `RunStore` 既是 append-only log 又是 idempotency cache

`RunStore.find_terminal_tool_invoked(idempotency_key)` 是线性扫描查找,为 PR6 resume dedupe 服务。append-only log 同时承担 idempotency 查询——单一职责破坏,且写时 O(n 注释自己承认 key is unique per envelope,留结构性预留。

### 10. `InsightEngine` 自己又维护了一份 mini RunStore

`_summaries: dict[str, dict]` 平行于 `RunStore._events`。两个 store 共同维护一个 trace 状态,schema 演化两边都得改。

### 11. `reducer.fold_run_state` 只算 RunStatus,token/步耗时/critical path 又被 InsightEngine 重算

同一份事件流,reducer 算 status,InsightEngine 又算 LLM calls/tokens/actions/latency——两个 fold 引擎,两遍扫描。

### 12. 同一"事实"被登记两次

`JournalEvent.DecisionMade` 在 `JournalCatalog`,`EventName.DECISION_MADE="decision.made"` 在 `TelemetryCatalog`,两个 catalog 各自维护 domain/emitter/required。`LlmCallStarted` 在 journal 是 `LlmCallStarted`,在 telemetry 没对应词汇(Started 不发 span);`RunInsight` 在两边都有。

### 13. `EventBus` 与 `make_journal_emitting_hook`(waterfall)并存

`layer1_cognitive/event_bus.py` 自称"emit/waterfall/serial 三模分发",`layer2_runtime/event_emission.py` 的 `make_journal_emitting_hook` 又做了"事件发射前拦截链",两者独立存在。

### 14. `attribute policy` 把领域语义写在 observability 层

`policy.py:_PREVIEW_KEYS` 是字符串白名单:`prompt_preview / response_preview / subtask_preview / objective_preview / memory_key_preview / rationale_preview`。新增预览字段必须去 policy 加白名单——observability 反向耦合到领域。

### 15. 双层属性策略

`RunStore._apply_policy` 在写入时做脱敏/截断/枚举归一;`SpanHandle.__exit__` 在退出 span 时又过 `policy.prepare`。同一份属性两次过 pipeline;逻辑重复(`_prepare_value` 与 `policy.prepare` 两处)。

### 16. `JournalProjector.flush()` 五种实现

| Projector | flush() |
|---|---|
| OtelProjector | no-op |
| InsightEngine | no-op |
| JsonlJournalProjector | `self._fh.flush()` |
| ConsoleJournalProjector | `self._stream.flush()` |
| SSEJournalProjector | no-op |
| LiveTail | no-op |

抽象契约 `JournalProjector.flush()` 的语义边界已经塌成"有的 flush 有的不动"。

### 17. `ObservabilityHub.release()/dispose()` 的二阶段语义

`release()` 关 store subscribers(jsonl/LiveTail),`dispose()` flush+shutdown exporters。组合根分两步调,但 Jsonl/LiveTail 是 subscriber,Langfuse 是 bridge,Otel 是 exporter——三种"可释放对象"叠在同一生命周期里。

### 18. `LiveTail.close()` 用 `queue.put_nowait(None)` 哨兵 + `SSEJournalProjector.close()` 用 `emit(None)` 哨兵

两种关闭信号协议在两个地方独立设计;`SSE_SENTINEL: None = None` 是命名常量化但又没约束类型。

---

## 二、架构优雅性

### 19. 嵌套 subscriber 解析是 lazy init hack

```python
self._store = RunStore(
    lambda: [InsightEngine(hub.store), OtelProjector(hub._tracer), *journal_projectors],
    policy=self._policy,
)
```

subscriber 需要 store,store 又包含 subscriber 列表。Lambda 捕获 self 是经典循环依赖破解——掩盖了"subscriber 应该是独立 service,不是 store 内部 list"。

### 20. `RunStore._validate_append_boundary` 在 runtime 重做 frozen 检查

事件已是 `frozen=True` dataclass,构造期就 frozen;RunStore.append 又 `getattr(type(event), "__dataclass_params__", None)` 检查 + `copy.deepcopy(event)`。deepcopy 是 O(事件字段大小) 的高频代价,只为"隔离"——但高频事件(`StepTextDelta`/`ReasoningDelta`)每次 write 都付。

### 21. 品牌化 ID 只在 spec 层,不强制

`RunScope.trace_id: TraceId = ""` 默认空串。`new_trace_id()` 工厂在 `atoms/ids.py`,但 `transport/invocation.py` 里 `cast(RunId, "")` ——品牌类型被显式绕过。

### 22. `derive_events` 缓存按 `id(predicate)` 分桶

predicate 是 lambda/local fn,CPython id 在跨进程或测试重启后变化。缓存命中率依赖"同一 closure object 被复用"——脆弱;且每次扫描仍是 `for e in self._events` 全量回放,没有时间窗口索引。

### 23. `Hub._actor_role / _actor_step` 用 ContextVar,但 `bind(hub)` 也是 ContextVar

5 个 contextvar 协同(`lca_obs_hub` / `lca_obs_session` / `lca_obs_actor_role` / `lca_obs_actor_step` / `lca_run_scope`)。嵌套 run 切换时必须每个 try/finally 配对 reset;缺一即泄漏。

### 24. `OtelProjector._delegation_parent` 的"就近 ambient"是 OTel 旁路

```python
ambient = otel_trace.get_current_span()
if ambient.is_recording() and not self._index.is_own_span(ambient):
    return ambient
```

绕过 OTel context propagation,自己用 span-id 比对判"是否本投影器创建"。这套机制是对 OTel 设计的反向覆盖。

### 25. `TracerProvider` 配置贫瘠

只有 `sampling_rate / service_name / environment`。生产要为不同 actor/team/loop 差异化采样、tag、namespace,没有 slot。

### 26. `ObservabilityBackend` 与 `Telemetry` Protocol 重叠

- `Telemetry`: span / event / score(发射)
- `ObservabilityBackend`: flush / close(生命周期)

业务层绑 facade 时类型不对齐。

### 27. `JournalFormatError` 是单一异常类型

jsonl 损坏 / schema 不匹配 / event_type 未知三种错误场景共用 `JournalFormatError(ValueError)`,无子类型。

### 28. `read_journal(path)` 一次性全量加载

jsonl replay 是 `path.read_text(...).splitlines()`,大 run 全量驻内存。没有 iterator/streaming 接口。

### 29. `ProcessJournal.publish` 用 `dataclasses.replace(stamped, seq=self._seq)` 改写 seq

`StampedEvent.seq` 是 ADR-0055 N2 不变量 `seq=log.length` 的承载字段;改 seq 破坏 N2,且 seq 还是 OTel projection 的 stable id 来源。

### 30. `JournalSink` 引入 `context_manifest_dual_write` 运行时开关

`if get_cognitive_loop_settings().context_manifest_dual_write: _journal_record(event)` 是 L0 配置驱动的行为分支,RunStore.append 与 facade.record 在不同条件下任一可走。

### 31. `event_emission._DERIVATIONS` 派生机制是 hook 名硬编码

`_DERIVATIONS: dict[HookEvent, Derivation]` ——新增派生事件要同时加 hook 名字符串键 + dataclass + journal.py + catalog.py + telemetry_catalog.py + emitter 字段。

### 32. `make_journal_emitting_hook` 的 waterfall 与 EventBus 同义

DSH-inspired 的拦截/修改/过滤链——同一概念(EventBus)在两个文件里各自实现,文档说"不再经 EventBus 中转"但模块未删除。

### 33. `diagnose_*` 4 个 if-else 分支

`diagnose_model_not_seen` / `diagnose_loop_stuck` / `diagnose_memory_poisoned` / `diagnose_approval_rejected` 是 4 个 free function,`diagnose()` 是 4 个 if-else 的 dispatcher。

### 34. `insight_rules` 阈值散落

`_REDUNDANT_MIN_COUNT=2` / `_LOOP_REPEAT_THRESHOLD=3` / `_LOOP_STEP_RATIO=0.8` / `_TOP_SLOWEST=3` 都是模块全局命名常量。无配置入口。

### 35. `LangfuseBridge.close()` 在 async 上下文里起 `threading.Thread`

`done.wait(2.0)` 超时 abandon,但 Langfuse SDK 自己的 shutdown 是阻塞的。

### 36. `Hub.score` 是 if-else 单数 slot

`self._scorer: ScorerFn | None`,多 scorer 时只保留最后注册,无注册表;fallback 是 emit_event。

### 37. `console_projector._state_of` 满 64 traces 后 FIFO 淘汰

`_MAX_BUFFERED_TRACES=64` 是上限但淘汰用 `next(iter(self._traces))` ——插入序 FIFO,不是 LRU;trace 满时随机丢最早的事实。

### 38. `LangfuseBridge.should_export_span` 与 Langfuse 服务端过滤器未声明关系

verbose 时 `lambda _span: True` 全过,但 Langfuse 服务端还有自己的 span filter。

### 39. `lca_ops logs` 没有 user-facing 格式选择

只有 `--verbose` / `--show-deltas` / `--replay` 三个开关,JSON / text / Mermaid 等输出格式由 FactStreamProjector 决定。

### 40. `RunStore.events` 每次访问复制

`return tuple(self._events)` 每次调用都建新 tuple——`ReadOnlySpanView` 风格但实际每次 O(n) 拷贝。

---

## 三、认知清晰度

### 41. 4 种"事实"在 console 并存

| 源 | 形式 |
|---|---|
| `JournalEvent` (StampedEvent) | 叙事平面 |
| OTel span | 机制平面 |
| OTel event | 机制事件 |
| `structlog.warning("xxx_failed")` | 基础设施日志 |

`diagnose_*` 在 console 上读时,这 4 种事实无视觉差异。

### 42. "Journal" 同时扮演三种角色

- 真源 (record-as-data, ADR-0037)
- 投影源 (所有视图 consumer)
- 控制原语 (ContextManifested 是 control primitive 的 journal 镜像)

"消灭双 owner"事实上 journal 同时是 owner + 控制信号源。

### 43. `DecisionMade.response_text` 与 OpenAI shim 的 response_text 语义滑动

journal 里 response_text 是"think 阶段产出";OpenAI shim 里 response_text 是"用户看到的内容"。同一名字在两处语义不同。

### 44. `ToolStarted` / `ToolCallStreaming` / `ToolInvoked` 三事件定义"工具调用生命周期"

- `ToolCallStreaming`: LLM 在 streaming tool arguments(OTel 视角)
- `ToolStarted`: 执行前(journal 视角)
- `ToolInvoked`: 执行后

三者次序、id 关联、字段约定散在三个 dataclass 的 docstring。

### 45. `LlmCallStarted` 是 `LlmCallCompleted` 的子集

- `LlmCallStarted`: step, model
- `LlmCallCompleted`: model, ok, latency_ms, prompt_preview, response_preview, prompt_tokens, completion_tokens, stream

Started 携带信息比 Completed 少一个数量级——Started 是冗余信号还是 checkpoint?没有 docstring 解释。

### 46. `RunActivity` / `RunInsight` 都是 post-hoc 观察

- `RunActivity`(LLM_THINKING / TOOL_RUNNING / SANDBOX_EXEC)是 `LlmStreamActivityTracker` 后台心跳的产物
- `RunInsight` 是 `InsightEngine` 收尾时的产出

两者都是"事后观察";但 `insight_engine` 自己重算 token/耗时,与 reducer 的 fold_run_state 不共享逻辑。

### 47. `StampedEvent.turn` 字段从未被填非零值

`turn=getattr(sanitized, "turn", 0) or 0` ——从事件自身取 turn 字段,但所有 JournalEvent 子类都不定义 turn。字段存在但永远 = 0。

### 48. `correlation_ids: tuple[str, ...]` 字段从未被消费

spec 写"multi-trace joining",序列化里保留,但 `RunStore` / `find_*` / 任何 projector 都不读 correlation_ids。

### 49. `audience="restricted"` 不在 OTel 真正 restricted

`ReasoningDelta` 在 JOURNAL_CATALOG_META 里 audience=restricted,只在 `is_sse_visible()` 阶段过滤 SSE 帧;OTel 投影链路不查 audience,reasoning 全文仍写入 OTel span。

### 50. `InboxFollowupCreated.payload_preview` 字段重复定义

```python
payload_preview: str = ""
payload_preview: str = field(default="", metadata={"journal_kind": "content"})
```

同一个字段定义两次,前面会被后者覆盖,两个默认值不同——python 不会报错但语义混乱。

### 51. `AttachmentStagingStarted.run_id` 与 `StampedEvent.scope.run_id` 重复

事件已有 `StampedEvent.scope.run_id`,`AttachmentStagingStarted.run_id` 是字段又一次声明;`AttachmentStagingFailed.run_id` 同样。

### 52. `ToolInvoked.idempotency_key` 与 `ToolStarted.idempotency_key` 没有强校验

两个事件都带 idempotency_key,字段存在但没断言:Started.key == Invoked.key。

### 53. `JournalSchemaMeta.sensitivity="confidential"` 与实际行为脱节

`confidential` 声明仅在 metadata,`policy.sanitize` 只 grep secret pattern;同一个事件,`sensitivity="public"` 与 `sensitivity="confidential"` 落盘 / 投影行为完全相同。

### 54. 三种语义同名字段 `step`

- `LlmCallStarted.step`: kwargs 传入的 step
- `StepTextDelta.step`: 常量参数
- `ReasoningDelta.step`: 常量参数
- `ToolStarted`: 无 step
- `DecisionMade.step`: state.step

step 在事件间不可严格比较——同一时刻多个事件的 step 可能不一致。

### 55. `LlmStreamActivityTracker` 在 no-bind facade 下还 tick 心跳

`record()` 是 no-op 时,后台 asyncio task 每 5 秒 `time.monotonic()` 检查 + 空 `record()` 调用——纯浪费。

### 56. `JournalProjector.close()` 后 on_event 行为"未定义"

协议 docstring:"close 后 on_event 行为未定义"。但 `process_journal` 把 LiveTail 塞进 `extra_projectors`,LiveTail.close 后 on_event 才被忽略——协议契约与实际行为不对齐。

### 57. `ResponseTextStreamExtractor` 跨职责放在 observability 包

文本增量解码 + JSON 字符串扫描是 LLM 输出解析,不是 telemetry。但放在 `observability/response_text_stream.py`。

### 58. `stream_channel.classify_output_channel` 是 deprecated 但还在

```python
def classify_output_channel(accumulated: str) -> str:
    """Deprecated heuristic classifier — always returns ``decision``."""
```

没删除时间表,仍被 `__all__` 导出。

### 59. `event_bus.py` 整模块还活着,AGENTS.md 说"不再经 EventBus 中转"

`emit / waterfall / serial 三模分发` 全在,但文档已声明 deprecated。

### 60. `run_narrative.py` 自我陈述"journal 已替代"

```python
"""span 树诊断渲染 —— 测试失败摘要用的里程碑过滤与单行格式化。
ADR-0037 后人类视图由 journal console 投影承担；本模块只剩 span 平面的
诊断工具（harness/report.py 在断言失败时渲染 span 树定位问题）。"""
```

"只剩"——但模块还在,被 export,被 narrative 包 re-export。

---

## 四、原语认知清晰度

### 61. `JournalEvent` 是空 dataclass 基类

```python
@dataclass(frozen=True)
class JournalEvent:
    """journal 事件基类（纯标记；领域字段在子类，关联骨架在 StampedEvent）。"""
```

文档说是"纯标记",但继承 dataclass 后子类字段不会再加到父类。Protocol / ABC 没用上。

### 62. 字段类型与 vocab 不一致

| 字段 | 文档枚举 | 实际类型 |
|---|---|---|
| `RunActivity.phase` | `RunActivityPhase` enum | `str = ""` |
| `StepTextDelta.channel` | `StreamChannel` enum | `str = "decision"` |
| `Insight.kind` | `INSIGHT_REDUNDANT_TOOL` 等常量 | `str = ""` |
| `GateDecided.gate` | `DecisionGateName` enum(只有 MUST_CONSULT_ALL/NONE) | `str = ""` |
| `JournalSchemaMeta.audience` | Literal | `Literal["end_user", ...]`(只有这个正确) |

5 个字段 enum 定义了但字段类型是 str,只有 1 个字段(Literal)严格。

### 63. 同一业务事件两种命名空间

- `JournalEvent.DecisionMade.__name__ == "DecisionMade"`
- `EventName.DECISION_MADE.value == "decision.made"`

`JOURNAL_CATALOG_META` 与 `TELEMETRY_CATALOG` 两表分别登记,但都是同一事件的"外部观察命名"。

### 64. `TeamRunStarted.objective_preview` vs `AgentRunStarted.objective_preview` vs `InboxFollowupCreated.payload_preview` 都用"preview"语义

`preview` 一词三用:`objective_preview` (TaskStatus 缩略)/ `payload_preview` (用户输入缩略)/ `prompt_preview` / `response_preview` / `rationale_preview` / `subtask_preview` / `memory_key_preview` (LLM/工具/记忆缩略)。`_PREVIEW_KEYS` 把这 6 个 key 都视为 preview,但语义不一致。

### 65. `RunScope` 的 `parent_run_id / parent_trace_id / delegation_id / agent_role` 默认值是 None / ""

品牌 ID 类型 + 默认空值。`adopt_run_scope` 三种返回路径里"是否 claim root"靠 `agent_role` 字符串判——空字符串是有效值(根 run)还是无效值(unbound)?

### 66. `TEAM_CONTAINER_ROLE = "team"` 是裸字符串常量化

`scope, _ = adopt_run_scope(role=TEAM_CONTAINER_ROLE)` ——团队容器的角色在源码里就是个字符串常量。无 `LeadRole` / `MemberRole` / `TeamRole` 类型层抽象。

### 67. `JournalSchemaMeta.audience` 与 `sensitivity` 的语义没在 writer 端强制

写入期 `RunStore._apply_policy` 不看 audience/sensitivity——只在 SSE 投影器与 consumer 端查 metadata。

### 68. `emit_tool_invoked` 的 `invocation_id` 解析双来源

```python
resolved_id = str((obs.extra or {}).get("invocation_id", "") or "") or invocation_id
```

先取 `obs.extra.invocation_id`,空则用函数参数 invocation_id。

### 69. `gate` 字段 5 处独立赋值

`record_gate_decided(state, GateDecided(gate="RepeatToolCallGate", ...))`——每个 gate 在自己文件里硬编码自己的类名字符串。

### 70. `LlmCallStarted.step` 字段与 stream channel 关系不明

`LlmCallStarted(step=kwargs.get("step", 0))` step 来自 kwargs;`StepTextDelta.step` 是常量参数;两者在同一 LLM 调用里可能不同——step 序列在事件间无序。

### 71. `ToolStarted` / `ToolInvoked` 都有 `arguments_preview` 但语义是相反的

- `ToolStarted.arguments_preview`: 即将执行的参数(预扣)
- `ToolInvoked.arguments_preview`: 已执行的参数(回顾)

同名字段在不同事件中表达"前/后"。

### 72. `SSEJournalProjector` 的 protocol 方法语义与现实使用脱节

protocol 定义了 `on_event/flush/close`,实现是"emit frame 或 None 哨兵",但实际生产路径完全走 LiveTail。

### 73. `process_journal` 的 seq 改写破坏了 OtelProjector 的时间线

```python
def publish(self, stamped: StampedEvent) -> None:
    self._seq += 1
    self.tail.on_event(replace(stamped, seq=self._seq))
```

原 stamped 已被 OtelProjector 用 seq 算过起止时间(基于 `stamped.ts - latency_ms`),现在 seq 改写后 LiveTail 消费者无法重建事件次序。

### 74. `JournalProjector` 是 `@runtime_checkable` Protocol

`@runtime_checkable` 意味着 `isinstance(x, JournalProjector)` 不会强制 duck-type 校验——子类不需要继承。Protocol 的存在只是文档作用。

### 75. `trace_id` 是 `TraceId` 品牌但 `cast(TraceId, caller_scope.trace_id if caller_scope else "")`

类型注解要求 `TraceId`,实际值是裸字符串。`new_trace_id()` 工厂是 `RunScope` 默认值,但 transport 里直接 `cast` 绕开。

---

## 五、其他系统性观察

### 76. `JournalProjector.flush()` 的"统一契约"完全空

5 个实现里 4 个是 no-op,只有 1 个(JsonlProjector)做 IO flush。

### 77. `RecordEvent` 没有独立 Protocol

`facade.record` 是 function;`RunStore.append` 是 method;`JournalSink.emit` 是 method;`RunStoreSink.emit` 也是 method。同一个"写 journal"行为,3 种入口签名,无统一 Protocol。

### 78. `RunStore.events` / `RunStore.get` / `RunStore.get_event` / `RunStore.get_blob` / `RunStore.find_terminal_tool_invoked` / `RunStore.derive_events` / `RunStore.read_from` 七种读 API

一个"append-only log"为什么需要 7 种读法?每种读法背后是一个 consumer;每个 consumer 应该自己 fold。

### 79. `RunStore.flush()` 与 `RunStore.close()` 的调用关系不明

`close()` 调 `flush()` 又调所有 subscriber 的 `close()`。如果 subscriber.flush 是 idempotent 无所谓;但 JsonlProjector.flush 是 `self._fh.flush()`,close 是 `self._fh.close()`,flush 后 close 是正确顺序,但 close 后再调 close 是 unsafe。

### 80. `Hub.dispose` 内 `force_flush(timeout_millis=2_000)`

硬编码 2 秒;不同后端(InMemory / Langfuse / Memory)能力不同,2 秒是 OTel SDK 默认,但没考虑 Langfuse 网络抖动。

### 81. `cognitive_agent.py` 的 try/finally 在 CancelledError 下收割 partial

`except CancelledError: drain_run_partial(); raise` ——`CancelledError` 在 Python 3.8+ 是 `BaseException` 子类,不会进 `except Exception`,必须显式 catch。但 finally 又 record Finished ——raise 时 Finished 已经 record,caller 再处理 CancelledError 时已经看到"已 Finished"事实。

### 82. `record()` 在 `team_message_tool` 被 alias 成 `_journal_record`

`from lca.infrastructure.observability import record as _journal_record` ——靠改名"遮蔽",reader 一眼分不清哪个 record 是 journal。

### 83. `run_narrative.py` 与 `plan_narrative.py` 在 narrative/ 子包,但前者是 span 诊断后者是 journal 模板

同一目录,完全不同的职责(一个渲染 OTel span,一个生成 journal 字段)。

### 84. `scripts/replay_journal.py` 与 `gateway/runs/cli.py:_replay_from_jsonl` 是两份独立 replay 脚本

`scripts/replay_journal.py` 用 `ConsoleJournalProjector`;`cli.py:_replay_from_jsonl` 用 `FactStreamProjector`。同一命令行工具,不同 verbosity 模型,不同输出格式。

### 85. `_BoundProcessJournal` 是 inline class,只在 `process_journal.py` 用

```python
class _BoundProcessJournal(JournalProjector):
    def on_event(self, stamped: StampedEvent) -> None:
        self._owner.publish(stamped)
```

一个适配 class,没有任何 override 的自由——可以直接 `ProcessJournal` 实现 `JournalProjector` 让 `bind()` 返回 self。

### 86. `JournalProjector` 的 `__init__` 自由度过高

`OtelProjector(tracer)` / `ConsoleJournalProjector(verbosity, stream=...)` / `JsonlJournalProjector(output_path)` / `SSEJournalProjector(emit)` / `LiveTail()` / `InsightEngine(store)` ——6 个完全不同的构造参数。

### 87. `_validate_append_boundary` 的 `copy.deepcopy(event)` 对 frozen dataclass 没必要

frozen dataclass 实例本身不可变,字段都是 immutable(tuple / str / int / bool)。deepcopy 是为未来 mutable 字段预留,现在做的是死成本。

### 88. `RunStore._apply_policy` 对 Enum 取 `.value` 但对其他 dataclass 不动

```python
if isinstance(value, Enum):
    updates[item.name] = value.value
    continue
if not isinstance(value, str):
    continue
```

混合类型策略:enum 归一、str 走 prepare、其他类型原样。三种处理路径在同一行。

### 89. `SpanHandle.__exit__` 对每个属性单独 `set_attribute`

50 个 attribute 是 50 次 OTel SDK 调用。

### 90. `record()` 是同步函数但 `append()` 也是同步

journal 写入全程同步(deepcopy、validate、policy、construct StampedEvent、notify subscribers)在事件循环里。`StepTextDelta` 每个 token 都进 record——单次 LLM 流式响应可能上千次 record。

### 91. `InsightEngine._emit_insights` 在 subscriber 的 on_event 里反向调 `store.append`

subscriber 回写 store——经典 anti-pattern。RunStore 用 `if isinstance(event, RunInsight): return` 防御性分支防自激。

### 92. `diagnose_loop_stuck` 与 `RepeatToolCallGate._consecutive_same_tool` 是两套"重复"语义

- diagnose 看 `ToolInvoked.tool_name` 线性扫描
- gate 看 `Decision.tool_calls[0].tool_name` 反向遍历 state.history

同一个"重复"概念,两个实现,不同语义(decision 视角 vs invocation 视角)。

### 93. `journal_io.stamped_to_record` 与 `sse_frames.stamped_to_sse_frame` 序列化路径重复

sse_frames 调 stamped_to_record 后包装 SSE 帧;jsonl_projector 直接调 stamped_to_record。

### 94. `__init__.py:journal/__init__.py` 只导 4 个符号

```python
from .engine import RunStore, UnregisteredJournalEventError
from .otel_projector import OtelProjector
from .reducer import RunState, RunStatus, fold_run_state
```

`ConsoleJournalProjector` / `JsonlJournalProjector` / `FactStreamProjector` 都不在 `journal/__init__.py` 的 export 里。

### 95. `tests/harness/collector.py:LiveCollector` 子类双构造

```python
def __init__(self, *, live: bool = True, detail: object = None) -> None:
    self._memory_exporter = InMemorySpanExporter()  # 1st构造
    ObservabilityHub.__init__(self, [self._memory_exporter], ...)  # 2nd 构造
```

父类 `InMemoryObservability.__init__` 已经构造过一次,子类跳过父类构造又自己造一份。

### 96. 5 个 ContextVar 协同无类型汇总

`lca_obs_hub` / `lca_obs_session` / `lca_obs_actor_role` / `lca_obs_actor_step` / `lca_run_scope` 各自独立;没有 `@contextmanager` 把它们绑成一组。

### 97. `process_journal.publish` 与 `_BoundProcessJournal.on_event` 是双跳

`on_event` 调 `owner.publish`,`publish` 又 `self._seq += 1; tail.on_event(replace(stamped, seq=self._seq))`——一层薄包装。

### 98. `LangfuseBridge.flush` 是 no-op

```python
def flush(self) -> None:
    """No-op. The SDK worker already exports; chat teardown must not wait."""
    return None
```

但 `ObservabilityBackend` Protocol 要求 flush——语义是"由后端决定何时 flush"。

### 99. `record_event_to_state` 与 `record(GateDecided(...))` 是两种 gate 注入路径

`chained.py:record_gate_decided` 调 `record_event_to_state(state, event)` 把 GateDecided 写进 `state.extra["gate_decided"]`(Perceive fold 用);`GateDecided` 本身在 journal.py 定义 dataclass,也有自己的"journal 镜像"职责。

### 100. `_error_message_max=500` 是 SpanHandle 的截断上限,但 `_GENERIC_STR_MAX=2_000` 是 policy 的上限,`_CONTENT_STR_MAX=50_000` 是 content 字段上限

三处数字不一致。

---

## 总览:核心张力

| 维度 | 核心张力 |
|---|---|
| 职责边界 | "Journal 是真源" 与 "Journal 又承担控制原语" 共存;"flush 是 no-op" 与 "flush 是协议方法" 共存 |
| 架构优雅 | 5 个 ContextVar 协同 + 9 步 record pipeline + deepcopy hot path + lazy subscriber 工厂 |
| 认知清晰 | 4 种"事实"并存 + 两套 vocab(Journal/Telemetry)登记同一概念 + 6 个"preview"字段被压成一档 |
| 原语清晰 | 5 个 vocab enum 定义了但字段类型是 str;品牌 ID 默认空串可被 cast 绕过;`StampedEvent.turn` / `correlation_ids` 永远默认值 |

## 最值得追问的前提

1. **`LiveTail` 真的属于 journal 投影器吗?** 它本质是 process-wide event broker,被借 JournalProjector 协议之名塞进 subscriber list。
2. **`record()` 同步写入 hot path 还能撑多久?** 一次 LLM 流式响应可能上千次 `record()`,每次都 deepcopy + validate + policy + 构造 StampedEvent——对长上下文场景的延迟影响没被测量。
3. **`JournalSchemaMeta` 把"分级"放 metadata 而不是机制**——分级是声明而非强制,意味着 `confidential` 标签事件真的不会被误传到非安全后端吗?
4. **两个 catalog 表(Journal/Telemetry)同步演化**——加一个事件要在两表分别登记,drift 风险大。
5. **`correlation_ids` / `StampedEvent.turn` 等"按需扩展字段"空跑**——schema 留口但实现从未填。