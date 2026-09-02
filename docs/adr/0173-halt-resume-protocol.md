# ADR-0173: halt-resume 协议 —— LoopCursor 对外 rescue 路径

## 状态

**Accepted — 2026-09-02**

> **实施状态(2026-09-02)**: ``StdLoopCursor.halt(reason)`` 仅锁 record_* /
> advance,保留 cursor 实例(0173 D1);``StdLoopCursor.resume_cursor`` 由
> spatial-temporal runtime 调用,派生新 cursor + 复用 spine handle
> (I-RESUME-1);``tests/observability/loop_cursor/test_halt_resume.py``
> 覆盖 halt/resume 状态机。Checkpoint replay 在 PersistenceCoordinator 仍占位
> (PR-15 边界) —— 0173 §D2 完整接 ``restore(from_seq)`` 待后续 PR。
> **不挂在 LoopCursor 内部异常路径**(评审山姆 §S10 + §潜在 #8):halt-resume 是独立协议,由 ADR-0171 ObservableRuntime + ADR-0093 Continuous Control Plane 协作。
> **回收自 ADR-0168-final §"不在本 ADR 范围"** 列第 7 项"halt 的 resume 协议"。
> **关联**: ADR-0065 L3 receipt sequence, ADR-0067 时空运行时, ADR-0093 Continuous Control Plane, ADR-0094 StopPolicy 局部性, ADR-0095 LoopGuard, ADR-0169 §D1 halt(reason), ADR-0171 Incarnation。

## 一句话

halt 是 "iteration 终止候选(reason=halt|loop_guard|approval_pending|approval_rejected)" 的可逆/不可逆二分;**resume 是 spatial-temporal runtime 的职责**(ADR-0067),"spawn next round" = 重建 `ObservableRuntime` + 派生新 `LoopCursor` with `IterationReason=checkpoint_resume`;**不复用** 已 close 的 cursor 实例。

## 背景

ADR-0168-final §"不在本 ADR 范围"列第 7 项 "halt 的 resume 协议",评审判定"halt-resume 宣称 in-scope 但机制薄,对 recovery profile 不够"。

具体痛点:

1. **halt 与 close 边界模糊**:都是"停止本轮 iteration",只是 close 释放资源、halt 留着尝试 resume。
2. **resume 复用 close 后的 cursor** —— `contextvar(loop_cursor)` 已经 clear,manifest_health 字段全是 None;trace 路径断。
3. **ad-hoc 协议**:旧 resume 走 `web-standard-recovery.yaml` profile + 一些列 `bind_*` 与 `restore_*` 函数,无显式契约。

正确分解(评审 §S10 处方):

| 关注点 | owner | ADR |
|---|---|---|
| 状态机 halt/close 区分 | LoopCursor Protocol | ADR-0169 §D1 halt(reason)|
| resume = 重建 Runtime 与 Cursor | Spatial-temporal Runtime 工厂 | 本 ADR §D2 |
| receipt sequence 不漂 | RunLedger (Incarnation)| ADR-0065 + ADR-0169 L14 |
| recovery profile 装配 | Profile-selected factory | ADR-0088 |
| checkpoint 重放 | PersistenceCoordinator | ADR-0170 D2 (`restore(from_seq)`)|

**核心命题**:**复用 cursor 实例 = 反模式**;resume = "析构旧 runtime + 派生新 runtime"。cursor 是 mutation 状态机,与"重建"语义天然冲突。

## 第一性原理

### P1 · resume 是重建,不是 reopen
stateful reopen 是 anti-pattern:ContextVar 残留 / Snapshot 已 freeze / Hook 链断;重建比 reopen 简洁且可证伪。

### P2 · halt 是 close 的子集,但有可逆 metadata
halt 携带 reason + 可恢复 trace_id + checkpoint_seq;close 释放一切。**状态机内部** halt 与 close 都是关窗 + 发信号;区别在 host / barrier 是否 wait_for_resume。

### P3 · recovery 不属于 loop
recovery 是 spatial-temporal runtime 的抽象(resume space → re-spawn time);loop 只负责关窗。

## 决策

### D1 · halt vs close 二元

| 维度 | halt(reason) | close(reason) |
|---|---|---|
| 资源占用 | cursor 实例保留,等待 resume;**不**触发 persistence flush | 完全释放;触发 L7 全流程 |
| resume 协议 | 用 `cursor.snapshot.checkpoint_seq` + `Incarnation` 重建 | 不可逆 |
| 适用 reason | `loop_guard` / `approval_pending` / `user_stop` (待 resume) | `completed` / `error` / `budget_exhausted` / `kernel_shutdown` / `user_stop` (终态)|
| ObservableRuntime 状态 | 持有(等 resume)| 已 dispose |
| ContextVar(loop_cursor) | 保留 | clear |
| LLMCallHook | 保留(unhook 在 resume 重接)| unhook |

**判定函数**(由 Profile 提供):

```python
# profiles/web-standard.yaml 段
halt_close_policy:
  loop_guard: "halt"
  approval_pending: "halt"
  user_stop: "halt"             # 默认 halt;close 是显式 opt-in
  approval_rejected: "close"
  error: "close"
  budget_exhausted: "close"
  kernel_shutdown: "close"
  completed: "close"
```

### D2 · resume 协议:`resume_cursor(reason: IterationReason = 'checkpoint_resume')`

```python
# infrastructure/observability/runtime.py
def resume_cursor(
    *,
    halted_cursor:    LoopCursor,        # 来自原 runtime(已 halt)
    iteration_reason: IterationReason,
    resume_ctx:       ResumeContext,     # 用户审批 / checkpoint / manual
) -> tuple[LoopCursor, ObservableRuntime]:
    """Resume 协议(本 ADR)。

    关键:不复用 halted_cursor 实例;析构 + 重建。

    1. 析构 halted_cursor 占用的资源:
       - unhook LLMCallHook
       - snapshot freeze(已发生)
       - host 不写新记录(view_snapshot 已被外部 reader 缓存可保留)
    2. 读取 halted_cursor.snapshot.checkpoint_seq
       + PersistenceCoordinator.restore(from_seq=...)
    3. 派生新 ObservableRuntime:
       - 复用 parent spine / persistence / host 实例(共享)
         或 派生 isolated_runtime(走 ADR-0171 §D3)
       - 新 Incarnation(parent.incarnation + 1, plan_ref 不变)
       - journal envelope 携带 iteration_reason = "checkpoint_resume"
    4. 派生新 LoopCursor from new runtime

    Returns (new_cursor, new_runtime).
    """
```

**核心数据结构**:

```python
# contracts/observability/resume.py
@dataclass(frozen=True)
class ResumeContext:
    iteration_reason:       IterationReason    # 必须 = "checkpoint_resume" | "user_replay"
    checkpoint_seq:         int                # halt 时 cursor.snapshot.seq
    approval_token:         str | None         # approval resume 才需要
    replay_seed:            int | None = None
    extra_headers:          Mapping[str, str] | None = None


@dataclass(frozen=True)
class ResumeReport:
    halted_cursor_id:       str
    new_cursor_id:          str
    iterations_resumed:     int
    durations_ms:           int
    trace_id:               str
```

### D3 · halt 流程 vs close 流程

```text
halt(reason) 走以下步骤(顺序由 LoopCursor 内部):

  1. 关状态机
       ├─ advance('stop') 完成;当前 step/segment/phase 窗口 emit window_end
       └─ 后续 record_* / advance 抛 CursorError

  2. cursor:发 writable.iteration.halt EP(带 reason)
       ├─ PersistenceCoordinator 接收 → 同步落盘 events.jsonl
       └─ ProjectionHost 接收 → host.view_snapshot() 冻结(snapshot freeze)

  3. cursor:保留 ObservableRuntime 引用(ContextVar(loop_cursor) 保留)
       └─ halted_cursor 被外部 resume 协议引用

  4. cursor 等待
       ├─ 外部 (Webserver route / user / scheduler / boot 等) 调用 resume_cursor(...)
       └─ 析构 + 重建(走 D2)

vs close(reason) 走 ADR-0169 §D5 五步(由 CloseBarrier 协调 flush)
```

**关键差异**:
- halt **不发** `writable.iteration.closing` / `writable.iteration.close` EP;发 `writable.iteration.halt` EP。
- halt **不**触发 `CloseBarrier`(CloseBarrier 在 close 时启用);halt 仅触发"redundant flush"——host.view_snapshot 冻结但 flush_all 不调。
- halt **不** unhook LLMCallHook;hook 仍连,等 resume 重用。

### D4 · Profile 配置:recovery-aware 装配

```yaml
# profiles/web-standard-recovery.yaml(profil-bundle 段)
runtime:
  halt_close_policy_override:
    user_stop: "halt"           # 默认 halt;旧 web-standard.yaml 用 "close"
  cursor_factory:
    resume_protocol:
      iteration_reason_default: "checkpoint_resume"
      enable_user_replay: true
      approval_resume:
        approval_token_validator: "lca.harness.approval.validate"
        retry_on_invalid: false

persist:
  spine_sink: { path: traces/runs/$RUN_ID/events.jsonl, best_effort_window_ms: 0 }  # halt 流程需要同步落盘
  restore_handler: "lca.infrastructure.persistence.checkpoint_restore"

host:
  initial: [step_tree, narrative, graph, cost, live_tail]
  # halt 流程:host 冻结 view_snapshot() 后,resume 时
  # view_snapshot() 状态连续(spine 已持久化,所以重新 drive 从 halt 后的 seq 开始)
```

**(钉死为何 recovery profile 是另一个 profile)**:`web-standard-recovery.yaml` 与 `web-standard.yaml` 的差异仅在 `halt_close_policy_override` + `cursor_factory.resume_protocol` 段;**结构上不能进 web-standard 默认 profile**(否则出了一种"事实可逆的 normal completion"——但 normal completion 永远 close)。

### D5 · LLMCallHook 与 ModelVisibleCapture 在 halt/resume 中的处理

```python
# adapters/telemetry_llm_adapter.py(扩)
class TelemetryLLMAdapter:
    def __init__(self, *, capture: ModelVisibleCapture, ctx: cordis.Context) -> None:
        self._capture = capture
        self._ctx = ctx
        # 在 cursor.attach() 时 hook ctor;在 cursor.close() 时 unhook
```

**halt 时**:
- `_capture.flush_artifacts()` 同步落盘(确保 model_visible/step_N 完整)
- LLMCallHook state 冻结(但 unhook 不执行)
- `cursor.record_request_header(...)` 在 halt 后 抛 CursorError(L5)

**resume 时**:
- 复用父 `_capture`(同一路径,新 step 序号自增)
- LLMCallHook state 由 `record_request_header(reason="series")` 自然重建
- `RequestHeader.inherited_from_step` 必填(指向最后一个 resume 前的 step)

### D6 · UI / API surface 落点

Webserver route 暴露给外部 approval / user replay:

```python
# lca/plugins/transport/webserver/handlers/runs/session/resume.py
def post_resume(run_id: str, body: ResumeRequest) -> ResumeReport:
    halted = lookup_halted_cursor(run_id)
    if halted is None:
        raise HaltedCursorNotFound(...)
    new_cursor, new_runtime = resume_cursor(
        halted_cursor=halted,
        iteration_reason=body.iteration_reason or "checkpoint_resume",
        resume_ctx=ResumeContext(...),
    )
    return ResumeReport(new_cursor_id=str(id(new_cursor)), ...)
```

## 决策差别 vs ADR-0168-final

| 关注点 | ADR-0168-final | 本 ADR |
|---|---|---|
| halt 单独控制入口 | cursor.halt(reason) | 同(继承 ADR-0169 §D1)|
| resume 协议 | 「不发 out-of-scope,但作为 is_scope 内凑合」 | **独立** resume_cursor(...) 协议 |
| cursor 复用 | 模糊(可隐式 reopen)| **禁止**:resume 永远派生新 cursor |
| approval_pending | close 五步 | halt 一流程 + reservation |
| host / persistence 复用 | 模糊 | 显式:复用 + 派生新 cursor |
| recovery profile 配置 | 模糊 | web-standard-recovery.yaml 显式 |
| UI/API 落点 | 模糊 | webserver `/runs/<id>/resume` |

## 不变量承接与新引入

| 既有 | 本 ADR 处理 |
|---|---|
| ADR-0065 L3 receipt sequence | 不变;resume 派生新 iteration_seq;原 seq 保留 |
| ADR-0067 时空运行时 | **强化**:resume 是 spatial-temporal 抽象的一阶公民 |
| ADR-0093 Continuous Control Plane | 兼容:`cursor_factory.resume_protocol` 与连续控制面共存 |
| ADR-0094 StopPolicy 局部性 | 不变:halt 由 profile policy 决定(本 ADR §D1)|
| ADR-0095 LoopGuard 局部性 | 兼容:loop_guard 在 halt 路径上 |
| ADR-0169 §D1 halt | 不变:halt(reason) 公开方法;**新增** reason 分类(D1)|
| ADR-0169 L14 incarnation | 不变:resume bump incarnation_seq |
| ADR-0171 fork 共享 Host | 兼容:resume 复用 parent runtime(spine / persistence / host)|
| **新引入 I-RESUME-1** | resume 必须派生新 cursor 实例,永不复用 halted_cursor |
| **新引入 I-RESUME-2** | halt 不发 `closing` / `close` EP,发 `halt` EP |
| **新引入 I-RESUME-3** | halt 时 persistence 同步落盘 best_effort_window_ms=0(L8)|
| **新引入 I-RESUME-4** | resume 时 host view_snapshot() 状态连续(从 halt 后的 seq 重新 drive)|
| **新引入 I-RESUME-5** | approval resume 必须带 approval_token;校验与 retry 显式 Profile 配置 |
| **新引入 I-RESUME-6** | web-standard 默认 close,recovery profile 才 halt 可恢复 |

## 兼容性

- web-standard.yaml 不增 resume 路径,行为不变。
- web-standard-recovery.yaml 与 web-standard.yaml 同步落地,但 runtime 默认是 close。
- 任何 profile 走 `halt_close_policy_override` 都显式 opt-in。
- 旧 ad-hoc resume 代码路径(`bind_*` / `restore_*`)走 PR-5 / S5 本 ADR 实施期 删除;删除条件 = `grep` 0。

## 删除条件

| 待删 | 条件 | 验证 |
|---|---|---|
| 旧 ad-hoc `bind_*` / `restore_*` 在 `execute/execution_environment.py` | 删除 | grep = 0 |
| 旧 `cursor.close(reason="resuming")` 异常路径(被 halt 替代)| 删除 | grep = 0 |
| 临时 `_legacy_halt_state` 字段(若实施期临时)| AST scan = 0 | `red_audit_log.jsonl` 必 0 |
| 旧 web-standard.yaml 的 "halt to close" user_stop 路径 | 删除(由 user_stop 走 halt_close_policy_override)| grep = 0 |

## 验证

```bash
# halt 不发 close EP
uv run pytest tests/observability/test_halt_emits_halt_ep.py -v

# resume 派生新 cursor
uv run pytest tests/observability/test_resume_new_cursor.py -v

# approval resume 校验
uv run pytest tests/observability/test_resume_approval_token.py -v

# web-standard 永不允许 halt 可恢复(user_stop close)
uv run pytest tests/profiles/test_web_standard_no_resume.py -v

# web-standard-recovery 跑通完整 halt-resume 流程
uv run pytest tests/profiles/test_recovery_profile_resume.py -v

# persistent 同步落盘(best_effort_window_ms=0)
uv run pytest tests/observability/test_halt_persistence_sync.py -v

# Incarnation 单调(resume = incarnation++ 同样适用)
uv run pytest tests/observability/test_resume_incarnation_monotonic.py -v
```

## 后果

### 正面

1. **resume 协议显式**:不再藏在 cursor.close() 异常路径。
2. **halt 与 close 二元**:Profile policy 决定,语义清晰。
3. **recover profile 独立装配**:`web-standard-recovery.yaml` 是合法独立 profile,不污染 web-standard 默认。
4. **API 落地**:`/runs/<id>/resume` 接口接受 iteration_reason + approval_token + replay_seed。
5. **receipt sequence + incarnation 单调** 与 ADR-0065 + ADR-0169 L14 一致。

### 负面

1. **新增 resume_cursor(...) API**:但语义清晰,与 ADR-0067 时空运行时一致。
2. **CLI / UI 整合**:外部 operator 需输入 iteration_reason 与 approval_token(在 webserver route 上接入)。
3. **recovery profile 实施需谨慎**:旧 `bind_*` / `restore_*` 必须 PR-6 删净,否则两条路并行更难维护。

## 引用

- ADR-0065 L3 receipt sequence
- ADR-0067 时空运行时
- ADR-0093 Continuous Control Plane
- ADR-0094 StopPolicy 局部性
- ADR-0095 LoopGuard 局部性
- ADR-0169 §D1 halt + L14 incarnation
- ADR-0170 ProjectionHost + CloseBarrier(L7)
- ADR-0171 fork 共享 Host(I-CURSOR-6)
- ADR-0169 §D11 阶段化实施第 5 阶段
- 实施计划: `docs/plans/2026-09-02-loop-cursor-control/0173-halt-resume.md`(由 writing-plans 输出)

---

## §附录 · 评审清单对照(山姆 §S10 + §潜在 #8)

| 评审点 | 本 ADR 落点 |
|---|---|
| halt-resume 宣称 in-scope 但机制薄 | ✅ 独立协议,不复用 close 异常路径 |
| 对 recovery profile 不够 | ✅ web-standard-recovery.yaml 显式装配 |
| resume 应诚实 out-of-scope | ✅ 范围锁在 halt / resume;不延伸到 budget / approval |
| 与 close 五步容易纠缠 | ✅ halt 不发 close EP;CloseBarrier 在 close 时启用 |
| LLMCallHook / Capture 残留 | ✅ D5 显式处理;resume 时 hook state 由 record_request_header 自然重建 |
| "在错的 step 里吐 fake 记录" | ✅ step_id + incarnation 由 cursor 注入;resume 派生新 cursor,新 step_id 自增 |
