# ADR-0072: Null-Default Discipline for Think Cluster and Memory Retrieval

## 状态

Proposed — 2026-08-21

Keeps: [ADR-0002](0002-cognitive-loop.md)、[ADR-0004](0004-protocol-first-pluggability.md)

> **核心决策：每个原语默认 no-op。`Critic` / `Synthesizer` / `RetrievalPolicy` 提供真 Null 默认；`SimpleCritic` / `ConcatSynthesizer` / `LayeredRetrievalPolicy` 由 bundle 显式装入。Think 群 Protocol 表面从 6 收敛到 4。**

## 背景

宪法 §3.4 规定三件套：原语 = Protocol + Null 实现 + 观察 hook；默认配置 = baseline 全 Null。当前实现违反此纪律：

**Think 群三个 trivial 模块：**

- `ModularBrain.think`（`lca/layer1_cognitive/brain/modular_brain.py:43–59`）17 行纯 sequencing wrapper：try_shortcut → skill_router → reasoner → build_decision → decision_gate → agent_gates，每行都是 delegation。
- `SimpleCritic.critique`（`critic.py:29–51`）23 行 `if observation.success: ... else: ...` 的字符串模板，reflection 语义权重大于实现。
- `ConcatSynthesizer.synthesize`（`synthesizer.py:21–53`）字符串拼接加分隔符。

Protocol 表面：Brain / Reasoner / Critic / Synthesizer / DecisionGate / SkillRouter 六个 seam，三个永远只 1 个 adapter。按宪法原则：一个 adapter = 假设性 seam；两个 adapter = 真实 seam。`Critic` 和 `Synthesizer` 从 v2 以来从未出现第二个实现。

**Memory 4 层拼接：**

- `SimpleMemorySystem.perceive`（`memory/simple_memory.py:80–104`）遍历全部 4 层（`for layer_name in self._private_layers: records.extend(...)`），`_shadow_compact` 走单一 budget=20 截断，`SimpleCompactionPolicy.compact`（`policy.py:174–192`）按 `recency_score` 取 top-budget，semantic 与 working 平等竞争。
- `MemoryLayer` 枚举（WORKING / SEMANTIC / EPISODIC / PROCEDURAL）作为接口存在，调用方必须知道四个名字（`SharedMemoryStore.is_shared(layer)` 接受 layer，`TeamSpec.shared_memory_layers` 按 layer 过滤）；检索策略完全不在乎记录来自哪一层。

宪法 §0.4 line 221 自承「记忆四层名字在，检索是拼接覆盖」。

## 决策

**Think 群：**

1. `Critic` Protocol 保留签名；新增 `NullCritic` 实现：`critique(state, observation) -> Reflection(verdict=ON_TRACK, lesson=None)`。不调用任何下游逻辑。
2. `Synthesizer` Protocol 保留签名；新增 `NullSynthesizer`：`synthesize(objective, candidates) -> candidates[0] if candidates else Result.failed(...)`。
3. `SimpleCritic` 与 `ConcatSynthesizer` 从 `lca/layer1_cognitive/brain/` 移入 `bundles/standard-think/brain.py`（或 `lca/plugins/think/` 下，作为 plugin 实现）。
4. `ModularBrain.reflect`（`modular_brain.py:61–62`）转为私有方法 `_default_reflect`；`Brain` Protocol 的 `reflect` 方法保留签名（供 custom Critic 注入），但 `ModularBrain` 默认实现调用 `self._default_reflect(state, observation)`（即原 SimpleCritic 逻辑），不暴露 Critic Protocol 给默认路径。
5. 默认 profile（baseline）装 `NullBrain`（已有 `NullBrain` 占位）+ `NullCritic` + `NullSynthesizer`；`standard-think` bundle 装 `ModularBrain` + `SimpleCritic` + `ConcatSynthesizer`。
6. Protocol 表面收敛：Brain / Reasoner / Critic / DecisionGate / SkillRouter / Synthesizer 6 个保留（替换接口契约），但 public seam 数量由 spawn 时解析的 factory 数量衡量。

**Memory retrieval：**

1. 新增 `RetrievalPolicy` Protocol，在 `lca/contracts/protocols/memory.py`：

```python
class RetrievalPolicy(Protocol):
    def retrieve(self, layers: dict[MemoryLayer, list[MemoryRecord]], budget: int) -> list[ContextCandidate]: ...
```

2. `NullRetrievalPolicy` 实现：`retrieve(layers, budget) -> []`。不参与任何 record 选择；上层应感知空 retrieval。
3. `LayeredRetrievalPolicy` 实现：
   - WORKING 永保留（不占 budget）
   - SEMANTIC + PROCEDURAL 按 `recency_score` 排序，共享剩余 budget 的 70%
   - EPISODIC 仅在 budget 剩余时填充，占 30%
4. `SimpleMemorySystem.perceive` 改为：

```python
async def perceive(self, state: AgentState) -> AgentState:
    candidates = self.retrieval.retrieve(self._private_layers_snapshot(), budget=_DEFAULT_MAX_WORKING)
    state.retrieved_context = candidates
    return state
```

5. 默认 profile 装 `NullRetrievalPolicy`；`standard-memory` bundle 装 `LayeredRetrievalPolicy`。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| §3.4 兑现 | Null 默认是真 no-op；think 策略与 retrieval 策略由 profile 显式声明 | 默认 profile 必须确认 Null 不引入回归 |
| ADR-0004 | Protocol-First 保留（Protocol 不删除） | 6 个 Protocol 中 3 个默认实现移位；spawn 解析路径不变 |
| 测试 | `tests/test_think_null.py` 断言 baseline profile 的 `NullCritic` 不写 lesson；`tests/test_memory_retrieval.py` 断言 working 永保留 + semantic 在 budget 压力下胜过 episodic | 老 SimpleCritic/ConcatSynthesizer 测试改 bundle fixture |
| 行为可见 | profile YAML 显示当前 think/retrieval 策略；`lca-ops inspect-tree` 可读 | profile 增加 think 与 retrieval 两个 bundle |

**验证约束：**

- `tests/test_code_conventions.py` 断言 `Critic` 与 `Synthesizer` 的 null 实现存在于 `contracts/protocols/` 同包
- 新增 `tests/test_think_null.py`：默认 profile 不调用 Critic；reflection.lesson is None
- 新增 `tests/test_memory_retrieval_null.py`：默认 profile `state.retrieved_context == []`
- `bundles/standard-think.yaml` 与 `bundles/standard-memory.yaml` 各自 round-trip 测试

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 保留 trivial wrapper（`SimpleCritic` 等）作为默认 | 违反宪法 §3.4「每个原语默认 no-op」 |
| 删除 `Critic` / `Synthesizer` Protocol | 违反 ADR-0004 Protocol-First；custom reflector / synthesizer 失去替换接口 |
| `RetrievalPolicy` 默认实现直接写 `LayeredRetrievalPolicy` | 等价于把策略硬编码进默认；与 §3.4 精神相反 |
| 把 `ModularBrain.reflect` 直接删除，调 `_loop` 走 `critic.critique` | 触发 ADR-0070 的 Brain 反射路径；两个 ADR 应同步落地 |
| 引入新的原语 `IndexingStrategy` 替代 RetrievalPolicy | v3 §3.2 已列 IndexingStrategy 作为 Memory 群内策略；保留原命名避免新增原语 |