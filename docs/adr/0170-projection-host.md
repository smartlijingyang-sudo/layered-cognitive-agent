# ADR-0170: ProjectionHost — Loop 维度可插拔投影宿主

## 状态

**Proposed — 2026-09-02**

> **Owner 不变量**: L9(ADR-0169 D3)。
> **关联**: ADR-0063 SSOT、ADR-0065 可恢复证据账本、ADR-0088 Profile-selected Runtime、ADR-0157 progress 流退役、ADR-0167 I-MV1 Model-visible ≡ Logged、ADR-0169 五缝架构的"投影缝"。
> **独立条件**:本 ADR 可独立实现 + 测试,前提是 ADR-0169 的`LoopCursor` Protocol 只持 spine handle,不持任何 Projection 字段。

## 一句话

`ProjectionHost` 是 **Loop 维度** 的可插拔投影宿主,与 ADR-0063 `ProjectionDefinition`(session 维度)并存;`StdLoopCursor` 不得持有投影引用,**新增 deriver 零改 `loop_cursor.py`**;CloseBarrier 协调 flush 顺序,L16 钉死 "ProjectionHost 不订阅 close EP"。

## 背景

ADR-0168-final §D6 把 `StdLoopCursor.__init__` 写成"spine + projections + persistence + llm_hook + model_visible 5 件套唯一装配入口"。评审判定这是 God Cursor:每加一种观测方式都要改 `loop_cursor.py`,回归面无限扩大(评审 §潜在 #1,§5.1)。

正确分解(评审 §3 + §7.1 推荐形):

| 维度 | 组件 | 引用 |
|---|---|---|
| Loop 维度投影 | **ProjectionHost**(本 ADR)| 5 件套 / step_tree / narrative / graph / cost |
| Session 维度投影 | `lca/contracts/harness/state/projection.py::ProjectionDefinition` | 既有,不重开 |
| LLM 边界真实捕获 | ModelVisibleCapture(本 ADR 不实现,在 D7 注释里引用 ADR-0172)| 5 件套由 Capture 写,ProjectionHost 持有事件流引用 |
| 关闭协同 | CloseBarrier(本 ADR 第四节)| L16 防投影已关竞态 |

**与 ADR-0063 的关系**:`ProjectionDefinition<K,S>` 协议保留为 **session 维度** 投影(SSOT 派生);本 ADR 新增 `LoopProjectionDefinition<S>` 作为 **loop 维度** 投影(状态机派生)。两者不互相替代,各负其责。

## 第一性原理

### P1 · 控制不持有观察实现
LoopCursor 只发语义事件;Host 监听事件并 reduce;cursor 不知道 Host 内部有什么 deriver(评审 S1 / S8)。

### P2 · 投影是纯函数/reducer
`apply(state, snapshot, record) -> state` 是纯函数 + 单一 seed;副作用(物化 journal.json / 写 narrative.md)由 `view(state) -> side_effect_target` 派生,不在 apply 内。

### P3 · 注册是 disposer 模式
`register(def) -> Token` 像 `ctx.effect()`:dispose 时自动从 snapshot 中消失。第三方 / 实验 deriver 不必进 cursor 发布流程(spine 仍是总线,评审 §S4 处方)。

### P4 · 与 spine SSOT 同构
Host 直接订 `EventSpine` 的 subscribers,而非持有 spine buffer(dsh 同构:consumer group 独立于 producer;Kafka 同构)。这条路保留事件总线的订阅可扩展性。

### P5 · Close 时序不是 cursor 责任
cursor 发 `writable.iteration.closing` 信号;CloseBarrier(独立组件) 协调"Persistence flush → Host.flush_all → 发 close EP → release"。L16 钉死 "close EP 不入投影" 防竞态。

## 决策

### D1 · LoopProjectionDefinition Protocol

```python
# contracts/observability/loop_projection.py

from typing import Protocol, Any, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class LoopProjectionSnapshot:
    """Projection 消费的只读视图。"""
    state:         Any
    seq:           int      # 最后一次 drive 的 event seq
    last_record:   Any      # 触发的最后一条 EventRecord
    monotonic:     bool     # 是否单调可重放


class LoopProjectionDefinition(Protocol):
    """Loop 维度纯 reducer。继承自 ADR-0063 ProjectionDefinition 思想;
    cursor 是事件源,projection 是订阅者(从 spine / snapshot)。"""
    key:     str           # registry 内唯一
    version: int           # schema version

    def init(self) -> Any: ...
    """seed 状态;每次 register 调一次。"""

    def apply(
        self,
        state:        Any,
        snapshot:     "CursorSnapshot",   # 来自 LoopCursor
        record:       "EventRecord",      # 来自 EventSpine
    ) -> Any: ...
    """纯 reducer;不抛副作用;in-place 修改禁止(返回新 state)。"""

    def view(self, state: Any) -> Any: ...
    """派生 side-effect target;Host.flush_all 调,在此才真正写 disk。"""

    def restore(self, state: Any) -> Any: ...
    """checkpoint replay 入口;默认 = init。"""
```

**与 ADR-0063 `ProjectionDefinition<K,S>` 的差别**:

| 维度 | loop(本 ADR) | session(ADR-0063) |
|---|---|---|
| 事件源 | LoopCursor.snapshot + EventSpine.record | Session / KernelTelemetryEvent |
| 状态语义 | step / segment / phase / iteration 内 / 单步派生 | session 全生命周期派生 |
| 投影例子 | StepTreeAccumulator / NarrativeDeriver / LiveTail | outcome summary / run totals / profile snapshot |

两套并存;不互相替代。

### D2 · ProjectionRegistry 实现

```python
# infrastructure/observability/spine/derivers/loop_projection_host.py

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProjectionHost(Protocol):
    def register(self, definition: LoopProjectionDefinition) -> Token: ...
    def unregister(self, key: str) -> Token: ...
    def drive(self, snapshot: CursorSnapshot, record: EventRecord) -> None: ...
    def view_snapshot(self) -> dict[str, Any]: ...
    def subscribe_changes(self, listener: Callable[[dict[str, Any]], None]) -> Token: ...
    def restore(self, *, base_seq: int, header: dict, cut: int) -> None: ...
    def flush_all(self) -> FlushReport: ...
    def close(self) -> CloseReport: ...


@dataclass(frozen=True)
class FlushReport:
    completed: tuple[str, ...]    # deriver key 列表
    failed:    tuple[tuple[str, Exception], ...]
    duration_ms: int


@dataclass(frozen=True)
class CloseReport:
    unhooked_subscribers: int
    dropped_events:       int     # 关闭后到达的事件(应当 = 0)
```

**关键契约**:
- `register(def) -> Token`(disposer);Token.dispose() 注销该 deriver(`ctx.effect()` 模式)。
- `drive(snapshot, record)` 由 **CloseBarrier** 在每次 `EventSpine.append` 后调用 —— 不是 cursor 直接调。
- `view_snapshot()` 返回派生视图,业务/SSE 走 `subscribe_changes(listener)`。
- `flush_all()` 由 CloseBarrier 在 step 3b 触发(L7 / D5);**每条 deriver 独立 try 隔离失败**。
- `close()` 在 L7 step 5 由 CloseBarrier 触发;之后到达的 `drive` 调用记录到 `dropped_events`,**不抛错**(计划评审要求:close 不应该导致业务 crash,但要可见的丢弃指标)。

### D3 · 默认注册清单(Profile 配置订阅;**不硬编码进 LoopCursor**)

| key | 用途 | 输出 |
|---|---|---|
| `step_tree` | step 物化 | `journal.json` |
| `narrative` | 人读叙事 | `journal.narrative.md` |
| `graph` | 阶段图 | `phase_graph.dot` |
| `cost` | 成本/预算 | `cost.json` |
| `live_tail` | SSE 当前态(纯 ring buffer) | 内部 ring + `subscribe_changes` 派生 |

**LiveTail 单身份(评审 §S4 + 附录 B 推荐形)**:
- 旧 LiveTail 同一对象是「ring buffer + pub/sub + JournalProjector + replay source」四身份 → 评审称"双轨残留"。
- 新 LiveTail 仅是 `LiveTailProjectionDefinition`:init = ring buffer,apply = append,view = snapshot。
- SSE 走 `subscribe_changes(listener)`:监听 `view_snapshot()` 变化,推 SSE(不持 SSE 状态)。
- replay source 走 `restore(...)` —— 不再从 LiveTail 抽。
- **`grep "_to_stamped"` = 0**(EP 名丢失 bug 修复)。

**可选 deriver(Profile YAML 选)**:
- `otel_trace`(走 ADR-0172 Exporter 实现层;不归本 ADR)
- `anomaly_detector`
- `live_tail_diff`(对比上一轮 iteration)

### D4 · L16 实现层钉死

```python
# infrastructure/observability/spine/derivers/close_barrier.py

class CloseBarrier:
    """协调 cursor.close 后的 flush 顺序。
    钉死不变量:
      L7-1 cursor 状态机 close
      L7-2 writable.iteration.closing EP emit
      L7-3 Persistence.flush() + sink close
      L7-4 ProjectionHost.flush_all()   ← 默认批写窗口
      L7-5 writable.iteration.close EP emit    (L16: 仅 Persistence 写入)
      L7-6 release

    L16 = L7-5 步骤的执行条件:
      close EP must be 写入 events.jsonl by Persistence;
      ProjectionHost.not_subscribe('writable.iteration.close') 由默认注册清单保证.
    """

    def __init__(
        self,
        *,
        cursor:          LoopCursor,
        spine:           EventSpine,
        persistence:     PersistenceCoordinator,
        host:            ProjectionHost,
        trace_id:        str,
    ) -> None: ...

    def coordinate(self, reason: CloseReason) -> CloseReport: ...
```

**为何不挂在 cursor**:`std::cursor::close()` 内部自带 flush 有"视图与执行耦合"问题;Barrier 解耦后,host/persistence 可换实现做故障注入(failure injection 测试,评审潜在 #16)。

### D5 · 装配入口

```python
# lca_kernel/observability.py(扩;与 ADR-0169 §D17 同源)
# profiles/web-standard.yaml 增 "loop_cursor" capability:
#   - projection_host: ProjectionHost(initial=[default_list...], profile=profile.yaml)
#   - persistence:     PersistenceCoordinator(coalescer, sink)
#   - model_visible:   ModelVisibleCapture (D7 ADR-0169)
#   - close_barrier:   CloseBarrier(...)

@dataclass
class ObservabilityRuntime:
    spine:           EventSpine
    cursor_factory:  LoopCursorFactory
    projection_host: ProjectionHost
    persistence:     PersistenceCoordinator
    capture:         ModelVisibleCapture
    barrier:         CloseBarrier

    @classmethod
    def from_profile(cls, profile: Profile, ctx: cordis.Context) -> "ObservabilityRuntime": ...

    @classmethod
    def from_test(cls, sink: InMemorySink, initial: list[LoopProjectionDefinition]) -> "ObservabilityRuntime": ...
    """in-memory profile for unit tests;评审 §5.1 处方."""


#RunSessionBuilder.build 不再"new StdLoopCursor 包办一切":
class RunSessionBuilder:
    def build(self, *, runtime: ObservabilityRuntime, run_id: str, ...) -> RunSession:
        cursor = runtime.cursor_factory.from_run_session(
            spine=runtime.spine,
            run_id=run_id,
            # ↓ 注意:cursor 不接受 host / persistence / capture 参数
        )
        runtime.barrier.attach(cursor)   # cursor.close → barrier.coordinate
        ctx = SessionContext(cursor=cursor, runtime=runtime)
        return RunSession(ctx=ctx)
```

**关键**:`StdLoopCursor.from_run_session` 签名**不含** host / persistence / capture 实例 —— 全部走 `CloseBarrier` 间接编排。AST 静态扫描 `runtime/loop_cursor.py` 即可断言 `_projections / _derivers / _persistence / _llm_hook / _model_visible_recorder` 字段全为 0(评审 S1 处方)。

### D6 · 词汇收口(EventDescriptor + cordis 收口,落 L12)

继承 ADR-0168-final §D14:cordis 不再是平行词表。

```python
# contracts/observability/event_descriptor.py
@dataclass(frozen=True)
class EventDescriptor:
    name:           str    # canonical name, e.g. "writable.step.start"
    cordis_name:    str | None
    phase_window:   tuple[str, ...] | None  # D7 钉死的允许 phase
    version:        int
```

spine 配置映射(由 Profile YAML 注入,不进 cursor):
```yaml
# profiles/web-standard.yaml 段
event_descriptor_cordis_translation:
  writable.step.start: null                # 不暴露给 cordis
  llm.request.header: "llm.request.header" # 走 cordis(供 hook 订阅)
  phase.act.fold.start:  "phase.act.fold"   # 走 cordis(供 live_tail / external)
  writable.iteration.close: null           # L16 仅 Persistence 消费
```

`spine.append(canonical_name)` 内部查表决定是否 `ctx.emit(cordis_name)`。

### D7 · 看 LLM 边界(与 ADR-0169 D7 + ADR-0172 协同)

> 本 ADR 不实装 ModelVisibleCapture,仅指定其与 Host / Capture 边界:
> - `Capture._write_step_artifacts(header: RequestHeader) -> dir` 由 LLM adapter 边界调用。
> - 写入 `model_visible/step_<NN>/{system,tools,messages,manifest,inherited}.json` —— ADR-0167 I-MV1。
> - `cursor.record_request_header(header)` 落 spine EP + digest —— cursor 不知道 Capture 存在。

LLM adapter 边界是唯一 capture 触发点(ADR-0169 D7);`Capture` 实例由 `ObservabilityRuntime` 持有,**不挂在 cursor**。失败 fallback 写到 host 错误指标(`projection_host.errors[...]=("model_visible", exc)`)而非 throw。

## 迁移(只摘重点)

| 现行 | 本 ADR 下 |
|---|---|
| `lca/infrastructure/observability/spine/derivers/step_tree_deriver.py`(既有)| 改实现为 `LoopProjectionDefinition.step_tree`,register 到 host |
| `bundles/spine-default.yaml` 19 plugin 含 deriver 列表 | 改为注册到 `ObservabilityRuntime.from_profile(...)` 的 `initial=[...]`;**不**作为 spine 子 plugin |
| `live_tail.py::_to_stamped` EP 名转换 | 删;`LiveTailProjectionDefinition` 直接收 `EventRecord` |
| `ProjectionRegistry.publish`(facade)| 删;统一调 `host.drive(snapshot, record)` |
| journal 写入双路径(`run_session_builder.subscribe` + `deriver.subscribe`)| 收成 ProjectionHost 注册 |

**保险措施**:实现期任一 deriver 暂不能 register 到 host,可暂时挂在 cursor 的 `_legacy_extra_drivers` 字段(RED,审计),记录 `host_register_failures.json` 备查;**禁止** 在 std 上保留更长。AST 扫描该字段为 0 才允许合并。

## 不变量承接与新引入

| 既有 | 本 ADR 处理 |
|---|---|
| ADR-0063 SSOT + ProjectionDefinition | **并存**:`ProjectionDefinition<K,S>` session 维度;`LoopProjectionDefinition` loop 维度 |
| ADR-0088 Profile-selected Runtime Factory | 扩:`ObservabilityRuntime.from_profile(...)` 是装配主入口 |
| ADR-0156~0158 投影隔离 | 一致;Host 持有投影,与 cursor 解耦 |
| ADR-0157 progress 流 | 不变;`live_tail.subscribe_changes` 派生 |
| ADR-0162 Fact vs Progress 准则 | 不变;Host.apply 落事实,view 派生 progress |
| ADR-0167 I-MV1 Model-visible ≡ Logged | 不变;Capture 在 LLM 边界,Host 引用 EP |
| **新引入 I-PROJ-1** | ProjectionHost.register(def).dispose() 必须从 snapshot 中消失 |
| **新引入 I-PROJ-2** | drive(snapshot, record) 由 CloseBarrier 调用,不是 cursor 直接调 |
| **新引入 I-PROJ-3** | flush_all 按 deriver 独立隔离失败;任何失败记录到 FlushReport.failed |
| **新引入 I-PROJ-4** | L16:ProjectionHost 不订阅 writable.iteration.close;集成测试断言 |
| **新引入 I-PROJ-5** | 新增 deriver 必须 **零改** `loop_cursor.py` 与 `close_barrier.py` |

## 兼容性

- 既有 `StepTreeAccumulator` / `NarrativeDeriver` / `GraphDeriver` / `CostProjector` 实现保留;改为继承 `LoopProjectionDefinition` 接口。
- `LiveTailProjectionDefinition` 单身份重构;旧 `_to_stamped` 删除,与评审 §4.1 移除味道一致。
- 不开兼容包装;inventory §11-7 EP 名丢失修复同时落地。

## 删除条件

| 待删 | 条件 | 验证 |
|---|---|---|
| `live_tail.py::_to_stamped` | 删除 | grep = 0 |
| `ProjectionRegistry.publish` | 删除(合并进 host.drive)| grep = 0 |
| `StdLoopCursor._projections` 字段 | 删除 | AST scan = 0 |
| `RunSessionBuilder.subscribe(...)` 调用 | 删除 | grep = 0 in `lca/plugins/transport/webserver/handlers/runs/session/builder.py` |
| 旧 `bundles/spine-default.yaml` 中的 deriver plugin | 删除(转 host `initial=[...]`)| grep = 0 in `bundles/` |
| `_legacy_extra_drivers` 字段(若实施期临时)| AST scan = 0 | `red_audit_log.jsonl` 必 0 |

## 后果

### 正面

1. **新增 deriver 零改 cursor**(评审 §5.1 处方):架构测试断言。
2. **Host 是订阅者,spine 是总线**(评审 §S4 处方):第三方 / 实验 deriver 可热插拔。
3. **L16 钉死防竞态**:CloseBarrier 协调,host 不订阅 close EP。
4. **失败隔离**:flush_all 按 deriver 独立 try;故障注入友好(评审潜在 #16)。
5. **session/loop 维度分清**:ADR-0063 与本 ADR 并存,语义不漂移。

### 负面

1. **新增 1 个组件**(Host + Barrier 2 个);但都是单一职责,各 < 200 行。
2. **旧 `LiveTail` 重写含 SSE 契约测试**(评审潜在 #13):SSE 回归期需要 1-2 个回归测试维度。
3. **`bundles/spine-default.yaml` 中的 deriver 转 host `initial=[...]`**:profile YAML 略调。

## 引用

- ADR-0063 Run Trace SSOT / ProjectionDefinition<K,S>
- ADR-0065 Recoverable Evidence Ledger
- ADR-0068 Compiled Plugin Kernel
- ADR-0074 Plugin-Everything
- ADR-0088 Profile-selected Runtime Factory
- ADR-0093 Continuous Control Plane
- ADR-0156~0158 projection 隔离与 finalizer 清理
- ADR-0157 Progress 流
- ADR-0162 Fact vs Progress 准则
- ADR-0167 Model-visible ≡ Logged
- ADR-0169 LoopCursor 控制面 + 五缝架构(本 ADR 是 "投影缝")
- ADR-0172 Observability Exporters 实现层(metrics/OTel 出口)
- 实施计划: `docs/plans/2026-09-02-loop-cursor-control/0170-projection-host.md`(由 writing-plans 输出)
