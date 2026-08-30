# ADR-0071: Composer-per-Cluster Plugin Decomposition

## 状态

**Partially Accepted — 2026-08-21（PR-5 / PR-10）**

**现行实现**：Composer Protocol + AgentGraph / TeamGraph frozen dataclasses 由 BrainComposer、BodyComposer、PerceiveComposer 与 TeamComposer 实现。TeamComposer 只依赖 `AgentAssemblyPort`；`PlanBoundAgentAssembler` 负责 profile plan 编译、图绑定、Agent 运行时闭合与 lead 预算提升。`lca/plugins/composer/{agent_assembly,plan_binding,runtime_factory,team_transport}.py` 承载组合 implementation，`lca/application/` 保留兼容导出与 spawn 门面。

Keeps: [ADR-0005](0005-composition-root-l4.md)、[ADR-0056](0056-plugin-group-contribution.md)、[ADR-0061](0061-plugin-manifest-resolve-boot.md)

> **核心决策：`spawn_agent` 是组合根门面，不持有装配策略。装配策略由 4 个 sub-composer plugin 承担，每个对应一个认知概念群；Brain/Body/Perceive/Team 各自的「如何连线」从 `spawn.py` 收敛到对应 sub-composer。**

## 背景

`lca/application/spawn.py` 是 L4 组合根门面：解析 booted scope、委托 `PlanBoundAgentAssembler` 闭合 Agent，并闭合 TeamHandle。plan 绑定、运行时构造、Team transport 与成员递归装配属于 `lca/plugins/composer/` 的 implementation。

具体摩擦：

- `_apply_lead_brain`（line 247–256）是全仓库唯一一处伸手进 Brain 内部（`brain.reasoner` / `brain.critic` / `brain.skill_router` / `brain.agent_gates`）的地方——其他模块按 Brain Protocol 边界访问。
- `_resolve_brain`（line 283–304）硬编码 BrainFactory 位置参数（`llm, profile, tools_desc, tools, available_skills`）；BrainFactory Protocol 新增参数时（[ADR-0005](0005-composition-root-l4.md) 强制所有参数显式声明）需要同时改 `_resolve_brain`。
- `build_perceive_hub`（line 207–233）手动解析 `journal_store` + `perceive` service + `skill_store`，调用 `service.assemble(memory, store=..., skill_store=..., team=...)`——assemble 逻辑应该在 service 内（ADR-0056）而非 spawn 内。
- TeamGraph 编排需要创建成员、transport、stage、lead 与 strategy，但 TeamComposer 不应通过 L4 `spawn_*` 重新进入组合根。

每个测试要 mock 整个 cordis Context 或构造真实 Context；组合根无法隔离测试。

## 决策

**Composer Protocol。** 在 `lca/contracts/harness/composer.py` 新增：

```python
class Composer(Protocol):
    key: ClassVar[str]

    def compose_agent(self, spec: AgentSpec, scope: Context) -> AgentGraph: ...
    def compose_team(self, spec: TeamSpec, scope: Context) -> TeamGraph: ...
```

`AgentGraph` 与 `TeamGraph` 是 frozen dataclass，持有封闭对象图（brain, body, memory, perceive_hub, hooks, state_store, stop_rule, runtime, observability）。

**Sub-composer Plugin。** 在 `lca/plugins/composer/` 新增 4 个 plugin：

- `plan_composers.py`：BrainComposer、BodyComposer、PerceiveComposer 与 TeamComposer 分别组装 think、act、perceive/memory 与 collaboration 概念群。
- `agent_assembly.py`：`AgentAssemblyPort` 是 TeamComposer 的递归装配 seam；`PlanBoundAgentAssembler` 是生产 adapter。
- `plan_binding.py` 与 `runtime_factory.py`：绑定 CompiledRunPlan，并把完整 AgentGraph 闭合为 CognitiveRuntime。
- `team_transport.py`：组装成员通道与内置 transport registry。

每个 sub-composer 由 `lca-plan-sub-composers` 在 boot 时注入。TeamComposer 以 `TeamComposer(PlanBoundAgentAssembler())` 接收生产 adapter；测试可注入确定性 adapter。

**`spawn_agent` 收缩。**

```python
def spawn_agent(spec: AgentSpec, *, scope: Context | None = None) -> CognitiveAgent:
    bound_scope = _ensure_scope(scope)
    return PlanBoundAgentAssembler().assemble_agent(spec, scope=bound_scope)
```

`apply_lead_brain` 属于 BrainComposer；`build_perceive_hub` 属于 PerceiveComposer。spawn 不访问 Brain 内部字段，也不承担 AgentGraph 或 CognitiveRuntime 的 implementation。

**Profile 化。** 默认 profile 装 4 个标准 sub-composer；科研 profile 可装自定义 `ResearcherBrainComposer`（保留 BrainFactory 协议约束）。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| ADR-0005 兑现 | L4 组合根 = 门面；装配策略 = plugin | 组合模块需要显式 seam 与 adapter |
| 测试 | TeamComposer 可注入确定性 AgentAssemblyPort | production adapter 仍需覆盖完整 profile 路径 |
| 替换 | 换 Agent 闭合策略 = 换 AgentAssemblyPort adapter | adapter 必须保持计划绑定和 capability 衰减 |
| Lead 构造 | lead 预算提升集中在 PlanBoundAgentAssembler | 触及 BudgetPolicy 的读取约定 |

**验证约束：**

- `tests/application/test_spawn_bind_plan.py` 覆盖计划绑定、缺失 composer、缺失 capability 与默认 profile Agent 闭合
- `tests/test_lead_composition.py` 与 `tests/test_shared_memory_isolation.py` 覆盖 lead 预算与成员共享记忆
- `tests/test_plugin_tree_single_owner.py` 覆盖默认 profile 的 sub-composer 注入
- TeamComposer 不得 import L4 `spawn` 或 `team_wiring`

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 把 `spawn.py` 拆成多个文件但不引入 Protocol | 复制今日硬编码装配模式，违反 ADR-0005 与 plugin-everything |
| 把装配策略推回 group service（让 `BrainService.assemble` 自己构造 Brain） | 模糊群贡献（ADR-0056）与装配策略的边界；group service 应只负责 membership 与 default |
| 保留 `_apply_lead_brain` 作为 spawn 内部辅助 | 违反 Brain Protocol 封装；任何 Brain 内部字段重命名都强制改 spawn |
| 把 spawn 改成完全 YAML 驱动 | 等价于 sub-composer 由 profile YAML 选择；可在 Phase B 实现，本 ADR 不阻塞 |