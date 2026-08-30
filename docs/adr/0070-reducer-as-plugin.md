# ADR-0070: CognitiveRuntime Reducer-as-Plugin

## 状态

**Accepted — 2026-08-21（PR-10 整合落地后接受）**

PR-4 / PR-10 整合落地：Reducer Protocol + DefaultReducer（apply_skill_route 等 seam）；C4 单一写守护（audit_state_writers 40 → 39）。

Keeps: [ADR-0002](0002-cognitive-loop.md)、[ADR-0005](0005-composition-root-l4.md)

Supersedes: 无（PR10 路线的提前落地，PRD §31 PR10 整并）

> **核心决策：`_loop` 是编排者，不是 state 写者。所有 state mutation 收敛到 `Reducer` Protocol，方法签名即 plugin seam；middleware 与 `_emit` 收口。**

## 背景

`lca/runtime/runtime_loop.py` 的 `_loop` 方法（line 201–283）有 14 处直接 `state.x = ...`，分散在感知、激活、终止、错误恢复、artifact closure 之间。宪法的 C4 规定 Reducer 唯一写 State，C5 + v3 §5.2 给出 Reducer 的形式契约。`_apply_manifest`（line 346–355）字面 `return state`，是形状合规但实际空转的 reducer；`_apply_activation`（line 331–343）注释自承「this function still touches state in place ... PR10 will convert」。

`_emit`（line 142–167）按 PR5 注释「return value is discarded by callers」，但调用者必须通过 `middleware_bag(state)["decision"] = decision`（line 231/237/245）把决策产物塞进 `state.extra["_middleware_bag"]` 才能让 middleware 读到——narrow seam 用 state 偷产物。Phase Middleware Registry 在 `lca/harness/middleware/registry.py` 完整实现，10 个 phase pre-registered，但 `grep "middleware_registry.register"` 0 hit——机制空转。

`_loop` 当前 AST 语句数 ~55，超过 ADR-0002 的 ≤30 目标。

## 决策

**Reducer Protocol。** 在 `lca/contracts/protocols/runtime.py` 新增 `Reducer` Protocol：

```python
class Reducer(Protocol):
    def apply_perception(self, state: AgentState, manifest: ContextManifest) -> AgentState: ...
    def apply_turn(self, state: AgentState, turn: Turn) -> AgentState: ...
    def apply_activation(self, state: AgentState, activated: tuple[ActivatedSkill, ...]) -> AgentState: ...
    def apply_memory(self, state: AgentState, writes: MemoryWriteSet) -> AgentState: ...
    def apply_stop(self, state: AgentState, stop: StopDecision) -> AgentState: ...
```

每个方法返回新 AgentState，不原地修改。`DefaultReducer` 实现作为 boot 默认；profile 通过 `ctx.provide("reducer", ...)` 覆盖。

**`_loop` 重写。** 编排者只调 Protocol：

```python
async def _loop(self, state, max_steps):
    for step in range(max_steps):
        state = self._reducer.apply_step_advanced(state, step)
        state = await self.perceive(state)
        decision = await self.brain.think(state)
        observation = await self.body.act(decision, state)
        reflection = await self.brain.reflect(state, observation)
        writes = await self.memory.propose(state, observation, reflection)
        state = self._reducer.apply_memory(state, writes)
        state = self._reducer.apply_turn(state, Turn(decision, observation, reflection))
        stop = self.stop_rule.decide(state, decision, observation, reflection)
        if stop.should_stop:
            state = self._reducer.apply_stop(state, stop)
            break
    return Result.from_state(state)
```

`_apply_manifest`、`_apply_activation`、`_apply_stop` 三个文件级辅助函数删除，调用方走 reducer。`memory.update` 拆为 `propose` + `reducer.apply_memory`，使 Memory 不再原地写 `_private_layers`。

**`_emit` 与 middleware_bag 收口。** 删除 `_emit` 整个方法、删除 `middleware_bag` 函数（line 64–76）、删除 `_MW_BAG` 常量、删除 `_SEAM_TO_HOOK` 与 `HOOK_SEAMS` 映射。`hooks.trigger(hook_name, state, **kwargs)` 在原 `_emit` 调用点直接展开。`CognitiveRuntime.__init__` 删除 `middleware_registry` 参数与 `self._mw` 字段。`spawn.py:236–244` 的 `_build_middleware_registry` 整个删除。

**LoopTopology Protocol。** 在 `contracts/protocols/runtime.py` 新增 `LoopTopology` Protocol：`phases() -> tuple[Phase, ...]`，每个 `Phase` 声明 `kind` ∈ {perceive, think, act, reflect, remember, stop}。默认实现 `ClosedSetTopology` 返回 C1 规定的六步闭集；profile 通过 bundle 装变体（PR6.D.5 finalize hook 等扩展不破闭集，由宪法纪律约束）。

**middleware 机制。** `lca/harness/middleware/registry.py` 与 `lca/contracts/harness/middleware.py` 删除；`lca/plugins/runtime/middleware.py` 卸载。middleware 路径若未来需要，由 hook + reducer 组合承担。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| C4 兑现 | 所有 state mutation 集中于 `Reducer` Protocol 实现 | Reducer 必须纯函数；存量 reducer 测试要改 fixture |
| ADR-0002 AST ≤30 | `_loop` 收敛到 ~15 行 | boot 时多一次 `ctx.require("reducer")` 解析 |
| PR10 提前 | middleware 与 `_emit` 收口提前完成 | 删 `middleware_bag` 与 SEAM_TO_HOOK 涉及 6 处调用点改写 |
| 性能 | reducer 返回新对象，触发 dataclass 拷贝——`AgentState` 当前为 mutable dataclass，切换为 frozen 是前置 | AgentState 转 frozen 涉及所有 `state.x = ...` 调用点（`_apply_artifact_closure` 等 ~10 处） |

**验证约束：**

- `tests/test_runtime_loop.py` 断言 `_loop` AST ≤30
- 新增 `tests/test_reducer.py`：5 个方法各自 unit test，纯函数（input state + event → output state）
- 删 `tests/test_middleware_bag.py`（如存在）
- `scripts/check_no_direct_state_mutation.py` 静态扫描 `_loop`/`perceive_hub`/`body.act`/`memory.update`/`memory.perceive`/`stop_rule` 内的 `state.x = ...` 字面

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 保留 `_apply_*` 文件级辅助函数，仅删 `_emit` | 仍违反 C4，且 reducer 形状被锁死在 runtime_loop.py，无法 profile 覆盖 |
| 把 `_loop` 整段交给 plugin（无 skeleton） | 违反 C1 六步闭集纪律——宪法 §4.1 要求闭集；plugin 可覆盖单步内容但不能换序 |
| 把 middleware 留着并强制注册一个 default | 仍是 dead infrastructure 的另一种形式；机制存在但无 2nd adapter 不构成真 seam |
| `AgentState` 不转 frozen，reducer 返回新对象但内部仍 mutate | 违反 v3 §5.2「Reducer 是纯函数」的契约 |