# ADR-0232 — `act.fanout` N:N + `ToolBatchExecutionMode.PARALLEL` Default for Read-Only Tools

**Status:** Accepted — 2026-09-16. PR-3.

> **一句话**：`act.fanout` 改为 N:N（接受 `envelopes: tuple[CommandEnvelope, ...]` typed port；N≥2 时 `next_hint="fanout_ntom"`），同时把 `ParallelReadOnlyToolBatchPolicy` 设为 read-only tool batch 的默认调度策略。两者一起把 5 个 read-only `runCommand` 从 220ms 串行降到 <200ms 并发。**不做 profile 回滚旗标**——PR-3 是硬切换，回归直接 revert。

**Refines / Fixes:**
- ADR-0228 §节点形态 — typed-port contract 复用；N:N fanout 是 typed port 图从 1:1 升级到 N:N 的最小化扩面。
- ADR-0219 §5.5 act_subgraph — `act.fanout` 由 1:1 扩为 N:N，保留 `fanout_1to1` 兼容单 envelope。
- ADR-0167 (spine SSOT) — `act.next_hint` 是 routing 决策非 EP，不入 C11 close-set；本 ADR 把 `fanout_ntom` 写为合法值，与 `fanout_1to1` / `fanout_empty` 并列。

## Problem

`act.fanout` 当前为 1:1 pass-through（`envelope → [envelope]`，`next_hint="fanout_1to1"`）。当 model 在一次 `Decision` 里 emit N 个 `tool_calls`，`act.envelope` 把 N 个 tool_calls 压成 1 个 envelope 串到 `act.fanout`，fanout 透传后 `act.dispatch` 串行送给 `SimpleSafeExecutor`，每个 tool 调完才下一个。

`run_feb0f21ee770` 实测：5 个 read-only `runCommand` 串行执行，wall time ≈ 220ms（5× 44ms 单次延迟），是 60-80ms gap 累加的结果。B-3：act.fanout 是 1:1 pass-through，`ToolBatchExecutor` 默认是 `SequentialToolBatchExecutionPolicy`，read-only 也没享受到 parallel。

### 根因（两层）

1. **act 拓扑层**：fanout 在 1:1 wiring 下吞掉了 N 这个维度；无论 model emit 几个 `tool_calls`，下游只看 1 个 envelope。
2. **body 执行层**：`ToolBatchExecutor` 默认串行；即便上游 fanout N:N 给出 N 个 envelope，`SimpleSafeExecutor` 内部也是按顺序逐个 await。

两层不同时改，无法去掉 220ms。

## Decision

### 1. `act.fanout` N:N typed port

`act.fanout` 接受 `envelopes: tuple[CommandEnvelope, ...]` typed port 输入：
- 0 envelope：`envelopes=[]`，`next_hint="fanout_empty"`（保持兼容）。
- 1 envelope：`envelopes=(e,)`，`next_hint="fanout_1to1"`（保持兼容）。
- N≥2 envelope：`envelopes=(e1,...,eN)`，`next_hint="fanout_ntom"`（新值）。

back-compat：若调用方只发 `envelope`（单值）端口而非 `envelopes` tuple 端口，fanout 仍按 1:1 处理。这是 typed-port graph 的语义继承，不要求 PR-3 同时把 `act.dispatch` 改成消费 tuple。

### 2. `ParallelReadOnlyToolBatchPolicy` 默认策略

新策略：`ParallelReadOnlyToolBatchPolicy`。
- 行为：仅当 batch 中**所有** tool call 的 `effects == "read"` AND grant 含 `concurrent` 子项时才 PARALLEL；否则 SEQUENTIAL。
- 替代当前默认 `SequentialToolBatchExecutionPolicy`，挂在 `ToolBatchExecutor` 构造的 `policy=` 默认值上。
- 显式声明 `effects="read"` 的 tool（runCommand、profile_diff 等）立即享受 parallel；`effects="write"`（file_write）/ `effects="external"`（bash）保持串行。

### 3. sandbox pool

N 个 read-only sandbox 调用通过 `lca/cognition/body/sandbox/pool.py` 并发执行，max-concurrency = `min(8, os.cpu_count())`（PR-3 默认 8）。pool 失败 contained——单个 sandbox 抛异常不影响同 batch 其他调用。

### 4. 无 profile 回滚旗标

- **不**新增 `act_fanout_mode=serial` / `tool_batch_mode=sequential` 等 profile knob。
- 回归路径：直接 revert PR-3（ADR 重置 `Proposed` → commit 回滚）。
- 理由：fanout_ntom / ParallelReadOnly 是显式 typed port 升级 + 显式 effects declaration，**没有静默回退的中间态**；加 knob 等于把过渡态永久化。

## Mechanism

| Layer | 改动 | next_hint / mode |
|---|---|---|
| act 拓扑 | `act.envelope` 1→N envelopes（typed port） | 不变 |
| act 拓扑 | `act.fanout` 接受 `envelopes` tuple | `fanout_ntom` (N≥2) / `fanout_1to1` (1) / `fanout_empty` (0) |
| body 执行 | `ParallelReadOnlyToolBatchPolicy` 默认 | PARALLEL iff all `effects="read"` AND grant.concurrent |
| body 执行 | sandbox pool | max-concurrency = `min(8, os.cpu_count())` |

```python
# act.fanout 新 typed port
declared_inputs: tuple[PortName, ...] = ("envelopes", "envelope")  # 双端口 back-compat
declared_outputs: tuple[PortName, ...] = ("envelopes", "envelope", "routing")

if envelopes is not None and len(envelopes) >= 2:
    next_hint = "fanout_ntom"
elif envelopes is not None and len(envelopes) == 1:
    next_hint = "fanout_1to1"
else:  # empty
    next_hint = "fanout_empty"
```

```python
# ParallelReadOnlyToolBatchPolicy
class ParallelReadOnlyToolBatchPolicy(ToolBatchExecutionPolicy):
    def select_mode(self, entries, effects, grants) -> ToolBatchExecutionMode:
        if all(e.effects == "read" for e in entries) and all(
            g.concurrent for g in grants
        ):
            return ToolBatchExecutionMode.PARALLEL
        return ToolBatchExecutionMode.SEQUENTIAL
```

## Invariants upheld

- **C1 认知闭集** — `next_hint` 是 routing 决策非 EP；`fanout_ntom` 是合法 next_hint 值，与 `fanout_1to1` / `fanout_empty` 并列；不扩 C11 事件闭集。
- **C2 双平面** — act 拓扑不改认知；body 执行保持 `cognition → Body → SafeExecutor → Sandbox` 窄门。
- **C4 Reducer 单写** — health deriver 读 routing 决策（`act_deriver` 升级 `fanout_ntom` 为 `ok`）；不写 State。
- **C5 capability monotonic** — `grant.concurrent` 是已有 C5 schema 子项；不扩 capability 三维。
- **C7 控制/观察分离** — fanout 是 topology 控制面；`next_hint` 是 routing 决策，下游 act.dispatch 据此消费。无观察面触发控制面副作用。
- **C9 幂等/重入** — N:N fanout 是纯函数（不读时间/全局）；sandbox pool 失败 contained。
- **C10 执行窄门** — `act.fanout` 仅做 N:N 重排；不调用 Body；不构造 envelope（除 act.envelope 节点）。
- **C11 事件闭集** — `next_hint` 不入 `EXECUTION_POINTS`；仍由 ADR-0233 escape-hatch 守护。
- **C13 信息血统闭合** — `envelopes: tuple[CommandEnvelope, ...]` 是 typed port（D1: 节点 declared_inputs；D2: 不可变 tuple；D3: 1:1 → N:N 转换链；D4: act.dispatch / act.observe 消费）。

## What changed

- `lca/nodes/act/fanout.py` — 新 `envelopes` 端口；`next_hint="fanout_ntom"` (N≥2)；保留 `envelope` 单值端口 back-compat。
- `lca/nodes/act/envelope/envelope.py` — 从 `decision.tool_calls` 产出 N 个 `CommandEnvelope`。
- `lca/cognition/body/tools/tool_batch_executor.py:99-135` — 默认策略替换为 `ParallelReadOnlyToolBatchPolicy`。
- `lca/cognition/body/tools/execution_policy.py` — 新策略类 `ParallelReadOnlyToolBatchPolicy`。
- `lca/cognition/body/sandbox/pool.py` — 新 sandbox pool（`min(8, os.cpu_count())` cap）。
- `lca/contracts/models/core/execution/tool.py` — `ToolApi.effects: Literal["read","write","external"]` 默认 `"external"`。
- `lca/plugins/tools/{bash,file_write,profile_apply,profile_diff,composio_tools}.py` — 显式 `effects=` 声明。
- `lca/contracts/cognition/body/tools/registry.py` — 新文件，registry schema 校验 `effects=` 必填。

## Out of scope

- `act.dispatch` 仍消费 `envelope` 单值端口（PR-3 不要求 N:N wire）；`act.fanout` 输出的 `envelopes` 端口作为 typed-port 备用值。
- `tool_batch_mode=sequential` profile knob — 见 §4 无回滚旗标。
- sandbox pool 失败重试 — 由 `SafeExecutor` retry policy 持有，不在 PR-3 范围。
- 跨进程的 sandbox pool（worker pool / k8s job）— PR-3 仅 in-process asyncio.Semaphore。

## Acceptance gate

- ADR 状态 Accepted ✓
- 8 derivers 持续工作；`act_deriver` 在 `next_hint="fanout_ntom"` 报 `ok`（PR-1 audit-run 集成测试无修改通过）
- 5 个 `runCommand` benchmark wall time <200ms（vs 220ms 串行）
- 6 个 pre-existing 失败保持不变
- 7d telemetry：`act.next_hint="fanout_ntom"` 频率；`tool.status=ok` rate vs `tool.status=failed`；零回滚请求
