# ADR-0171: fork 共享 Host 协议 —— child cursor 不持独立 Host 实例

## 状态

**Accepted — 2026-09-02**

> **实施状态(2026-09-02)**: ``StdLoopCursor.fork`` 仅共享 spine handle,
> child 不持独立 host / persistence / capture 实例(0171 D1 / D6);
> ``Incarnation.child()`` 在 fork 时递增 ``incarnation_seq`` 并继承
> ``run_id + plan_ref``(``tests/observability/loop_cursor/test_fork_shared.py``
> 覆盖)。fault-isolated subagent 走 ``IsolatedSubagentRuntime`` 协议
> 仍待 PR-25 后续补。
> **Owner 不变量**: I-CURSOR-6(ADR-0169 新引入)。
> **关联**: ADR-0065 Recovery(冷读 subagent)+ ADR-0093 Continuous Control Plane + ADR-0094 StopPolicy 局部性 + ADR-0165(.1) Execution Point Enforcement + ADR-0169 五缝架构的"fork 横切"。

## 一句话

子 cursor(**fork()** 派生)不持独立 `ProjectionHost` / `PersistenceCoordinator` 实例,**默认共享 parent 的 Observable Runtime**(host、persistence、capture、spine 引用);如需分裂(例如 fault-isolated subagent),走显式 `IsolatedSubagentRuntime` 协议。`Incarnation` 在 fork 时继承 parent 的 `run_id + plan_ref`,`incarnation_seq = parent + 1`。

## 背景

ADR-0168-final §"不在本 ADR 范围"列第 6 项 fork() 实装,本 ADR 在评审山姆 §潜在 #8 处置:

> child fork 复制 Host / 未设计共享 / 内存/重复文件/重复 SSE

深拷贝(每个 child cursor 自带一套 ProjectionHost + Persistence + Capture + LiveTail ring)会让子 agent 出现:

1. **重复 flush**:child 各自跑 Persistence.flush,事件同一份却落 N 次(events.jsonl 行数翻倍或 fan-out 锁竞争)。
2. **重复 SSE**:LiveTail ring buffer 每次 fork 复制,UI 看到 N 份重复流。
3. **子 cursor 与 host 生命周期错配**:child close → host.close,但 parent run 还在跑 → projection 关闭错误时序。

正确分解:

- **默认浅共享**(host / persistence / capture / spine 引用):parent 拥有 runtime;child cursor 只持 cursor + span context。
- **故障隔离**(fault-isolated subagent):显式 `IsolatedSubagentRuntime(ctx)` 协议,新建 host 实例。

## 第一性原理

### P1 · cursor 是控制状态机,不是 runtime owner
fork 派生新状态机;runtime(spine / host / persistence)由 ObservabilityRuntime 拥有,与 cursor 生命周期独立。

### P2 · 派生是因果派生,不是所有权吞并
fork 派生新 cursor;其视野(parent run_id + parent plan_ref + incarnation_seq++)由 cursor 派生,不由 runtime 派生。

### P3 · 默认低开销,隔离显式 opt-in
90% 用例需要"共享 parent runtime"(轻量派生);10% 用例需要"独立 runtime"(故障隔离)。协议位默认前者,后者显式协议。

### P4 · incarnation 是计划身份,iteration 是尝试计数
fork → incarnation_seq += 1;同 plan 内重试 iteration += 1。两者正交。

## 决策

### D1 · fork 默认共享协议

```python
# contracts/observability/loop_cursor.py
class LoopCursor(Protocol):
    def fork(self, reason: Literal["child_agent", "delegation"]) -> "LoopCursor": ...

# contracts/observability/incarnation.py
@dataclass(frozen=True)
class Incarnation:
    run_id:          str
    plan_ref:        str
    incarnation_seq: int

# infrastructure/observability/runtime.py
@dataclass(frozen=True)
class ObservableRuntime:
    """parent 与 child 共享的 runtime 句柄。"""
    spine:           EventSpine
    projection_host: ProjectionHost
    persistence:     PersistenceCoordinator
    capture:         ModelVisibleCapture
    close_barrier:   CloseBarrier
    runtime_id:      str          # identity 不同 ≠ runtime 实例不同


class LoopCursorFactory(Protocol):
    def from_run_session(
        self,
        *,
        run_id:     str,
        trace_id:   str,
        spine:      EventSpine,
        # 不接受 host / persistence / capture 参数 —— 共享 parent
    ) -> LoopCursor: ...

    def from_runtime(
        self,
        runtime:    ObservableRuntime,
        *,
        run_id:     str,           # = parent.run_id? 看 D2
        plan_ref:   str,           # 通常继承 parent
        incarnation_seq: int | None = None,  # 默认 parent + 1
    ) -> LoopCursor: ...
```

**默认行为**:
- child cursor 通过 `LoopCursorFactory.from_runtime(parent_runtime, ...)` 构造。
- child cursor **不接受** `ProjectionHost` / `PersistenceCoordinator` / `Capture` 注入 —— 这些从 `parent_runtime` 取。
- `Incarnation.run_id = parent.run_id`;`Incarnation.plan_ref = parent.plan_ref`(除非显式覆盖)。
- `Incarnation.incarnation_seq = parent.snapshot.incarnation + 1`。

### D2 · run_id 与 trace_id 的 fork 语义

| 用例 | run_id | trace_id | incarnation_seq |
|---|---|---|---|
| subagent(同 run)| = parent.run_id | 子 span id(OpenTelemetry 规范)| parent + 1 |
| delegation(独立 run)| **= parent.run_id**(本 fork 内)| 子 trace id | parent + 1 |
| checkpoint resume | = parent.run_id | 不变 | 不变(fork 不增)|

**注**:ADR-0065 §L3 "replay decisions require the original receipt sequence" 要求 incarnations 单调;fork 是"原 receipt 之后的派生" —— 派生的 detail 由 journal envelope 区分(ADR-0169 L14)。

### D3 · 故障隔离显式协议 `IsolatedSubagentRuntime`

```python
# infrastructure/observability/runtime.py
@dataclass
class IsolatedSubagentRuntime:
    """显式 opt-in 的独立 runtime;用于 agent 故障隔离或独立 SSE 订阅。

    共享的部分:
        - 父 run_id 的 manifest snapshot(只读 metadata,不是 projection)
        - 父 trace 引用链

    不共享的部分:
        - 新 EventSpine(指向 traces/runs/<run_id>/<child>.spine.jsonl)
        - 新 ProjectionHost(独立 SSE 端点)
        - 新 PersistenceCoordinator(独立 coalescer)
        - 新 ModelVisibleCapture(独立捕获本地)
        - 新 CloseBarrier
    """
    parent_run_id:     str
    child_run_id:      str
    child_trace_id:    str
    isolated_spine:    EventSpine
    isolated_host:     ProjectionHost
    isolated_persist:  PersistenceCoordinator
    isolated_capture:  ModelVisibleCapture
    isolated_barrier:  CloseBarrier


@runtime_checkable
class LoopCursorFactoryIsolated(Protocol):
    def from_isolated_runtime(
        self,
        isolated: IsolatedSubagentRuntime,
        *,
        plan_ref: str,
        incarnation_seq: int | None,
    ) -> LoopCursor: ...
```

**用法**:
- 普通 subagent 走 `runtime.cursor_factory.from_runtime(parent_runtime, ...)`(默认)
- 故障隔离 subagent 走 `runtime.cursor_factory.from_isolated_runtime(IsolatedSubagentRuntime(...), ...)`(显式 opt-in)
- 判定**显式 vs 隐式**不在 cursor,不在 host,在**Profile 配置**(`subagent_runtime_isolation: shared | isolated_by_default`)。

### D4 · SSE 与 LiveTail 共享机制

parent 与 child 共享同一 `ProjectionHost`,LiveTail 是 `LiveTailProjectionDefinition`,其 ring buffer 是 **per-host** —— parent + 共享 child 看到同一 ring;`incarnation_seq` 作为 key 区分。

```python
# tests/integration/sse/test_fork_shared_live_tail.py
def test_fork_shared_live_tail_emits_one_ring():
    parent_runtime = make_runtime(host_defs=[LiveTailProjectionDefinition()])
    parent_cursor = parent_runtime.cursor_factory.from_runtime(parent_runtime, run_id="r1", ...)
    child_cursor = parent_cursor.fork("delegation")
    # 模拟 parent 与 child 各自 record
    parent_cursor.record_thinking(...)
    child_cursor.record_tool_call(...)
    # host.view_snapshot() 包含 parent 与 child 的所有 record;
    # 没有两份 ring,没有重复 SSE
    assert parent_runtime.projection_host.view_snapshot()["live_tail"]["entries"] == [
        {"incarnation_seq": 1, "phase": "think", ...},
        {"incarnation_seq": 2, "phase": "act",   ...},
    ]
```

**关键**:`record_*` 落 event 携带 `incarnation_seq`(ADR-0169 L14);LiveTail ring 按 seq 索引;同一 host 同一 ring → SSE 不重不漏。

### D5 · Persist 事件流与 file-lock

共享 `PersistenceCoordinator` 意味着同一 spool + 同一 coalescer + 同一 storage:

```text
parent.cursor ─┐
                ├─→ shared_spine ─→ shared_persistence.flush
child.cursor ──┘                  (single coalescer batched write)
```

`flush` 由 CloseBarrier 在 close 时统一调(ADR-0170 D4 L7-3);child cursor 的 close 不触发独立 flush(共享 host 的 barrier 协调整个 tree 的 order)。

**file 路径**:即使共享 persistence,child cursor 的事件也只入 `traces/runs/<run_id>/events.jsonl`(单写 L10)。绝不复制到 `events_child.jsonl`(ADR-0169 L10 + ADR-0063 SSOT)。

### D6 · incarnation 与 IterationReason

```python
# cursor 内部
def fork(self, reason: Literal["child_agent", "delegation"]) -> "LoopCursor":
    parent_snapshot = self.snapshot
    new_incarnation = Incarnation(
        run_id=parent_snapshot.run_id,
        plan_ref=self._incarnation.plan_ref,
        incarnation_seq=parent_snapshot.incarnation + 1,
    )
    new_cursor = self._factory.from_runtime(
        self._runtime,                  # 共享 runtime
        run_id=parent_snapshot.run_id,
        plan_ref=self._incarnation.plan_ref,
        incarnation_seq=new_incarnation.incarnation_seq,
    )
    # journal envelope 自动携带 incarnation(ADR-0169 L14)
    self._spine.append(
        execution_point="loop.fork",
        payload={"reason": reason, "child_incarnation": new_incarnation.incarnation_seq, ...},
        incarnation_seq=new_incarnation.incarnation_seq,
    )
    return new_cursor
```

**IterationReason** 由 child 用:`subagent_resume` 显式 stamp;默认 null。

## 决策差别 vs ADR-0168-final

ADR-0168-final §"不在本 ADR 范围 fork() 实装"中描述"完整继承 parent.run_id + parent.plan_ref"——本 ADR 继承此,**但**新增:
1. 共享 vs 显式隔离两个协议位(ADR-0168-final 未区分,只说"从 parent 继承");
2. SSE 与 LiveTail 单 ring(继承默认 host 注册);
3. Persist 流 spine SSOT 单写(继承 ADR-0169 L10);
4. **`assertion`**:child cursor 实例字段白名单(§验证)。

## 不变量承接与新引入

| 既有 | 本 ADR 处理 |
|---|---|
| C5 能力衰减 | **强化**:child 持 parent run_id;child 的 capability grant ⊆ parent grant |
| ADR-0065 L3 持久 receipt sequence | 不变;incarnation_seq 单调 |
| ADR-0088 Profile-selected Runtime Factory | 继承:`subagent_runtime_isolation` 由 Profile YAML 决定 |
| ADR-0093 Continuous Control Plane | 继承;`from_runtime` 不破坏 control plane 装配 |
| ADR-0094 StopPolicy 局部性 | 继承;child cursor.halt 不影响 parent |
| ADR-0169 L14 incarnation | 钉死实现;child fork 必 bump incarnation_seq |
| **新引入 I-FORK-1** | child cursor 不持独立 host / persistence / capture 实例(默认 shared) |
| **新引入 I-FORK-2** | 显式 opt-in 走 `from_isolated_runtime(...)`;opt-in 由 Profile 决定 |
| **新引入 I-FORK-3** | 共享 runtime:同一 `incarnation_seq` 全是同一 host 中 |
| **新引入 I-FORK-4** | child cursor.close 不触发独立 flush;barrier 协调整个 tree 的 flush 顺序 |

## 兼容性

- ADR-0169 §D1 fork() 占位协议被本 ADR 充实实现细节。
- `LoopCursorFactory.from_runtime` 是新增入口;旧的 `from_run_session` 保留作 historical 入口(只在 web-standard 的 non-fork 装配路径用)。
- `IsolatedSubagentRuntime` 是新协议位;Profile 默认 `shared`,故障隔离子 agent 需显式 + YAML `subagent_runtime_isolation: isolated_by_default` 或运行时覆盖。

## 删除条件

| 待删 | 条件 | 验证 |
|---|---|---|
| 旧 `cursor.fork(...)` 内部 `_clone_subscribers` / `_copy_persistence` 代码 | 删除 | grep = 0 |
| `LiveTailRingBuffer` 双重构造路径 | 删除 | grep = 0 |
| 临时 `_legacy_isolated_cursor_state` 字段(若实施期临时)| AST scan = 0 | `red_audit_log.jsonl` 必 0 |

## 验证

```bash
# 默认共享用例:parent + child 同 ring
uv run pytest tests/observability/test_fork_shared.py -v

# 显式隔离用例
uv run pytest tests/observability/test_fork_isolated.py -v

# child cursor 字段白名单断言
uv run pytest tests/observability/test_fork_cursor_field_whitelist.py -v
# assert "child_cursor._projections" not in vars()
# assert "child_cursor._persistence" not in vars()
# assert "child_cursor._host" not in vars()

# SSE 不重复
uv run pytest tests/observability/test_fork_shared_live_tail.py -v

# incarnation 单调
uv run pytest tests/observability/test_incarnation_seq_monotonic.py -v
```

## 后果

### 正面

1. **child cursor 零成本派生**(对照 ADR-0168-final 深拷贝场景):共享 runtime,不复制 host 状态。
2. **SSE / LiveTail 单 ring**:不重不漏,UI / 调试器一致视图。
3. **incarnation 单调**:journal envelope + record seq 一致;replay 时 iteration 边界可重建。
4. **故障隔离显式 opt-in**:默认共享,opt-in 隔离;Profile YAML 控制。

### 负面

1. **新增 `ObservableRuntime`** 类型 + 协议位:但语义清晰,与 ADR-0169 §D8 一致。
2. **故障隔离路径需新增 `IsolatedSubagentRuntime`**:但只在确实需要时引入,不污染默认共享路径。
3. **child cursor.close 与 parent cursor.close 时序** 需要 CloseBarrier 协调(tree 顺序):但 ADR-0170 L7 已规定。

## 引用

- ADR-0065 Recoverable Evidence Ledger
- ADR-0088 Profile-selected Runtime Factory
- ADR-0093 Continuous Control Plane
- ADR-0094 StopPolicy 局部性
- ADR-0095 LoopGuard 局部性
- ADR-0165(.1) Execution Point Enforcement
- ADR-0169 LoopCursor 控制面 + L14 incarnation
- ADR-0170 ProjectionHost + CloseBarrier
- ADR-0172 Observability Exporters
- 实施计划: `docs/plans/2026-09-02-loop-cursor-control/0171-fork-shared-host.md`(由 writing-plans 输出)
