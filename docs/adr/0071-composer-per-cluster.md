# ADR-0071: Composer-per-Cluster Plugin Decomposition

## 状态

**Partially Accepted — 2026-08-21（PR-5 / PR-10）**

**PR-5 落地**：Composer Protocol + AgentGraph / TeamGraph frozen dataclasses；4 sub-composer implementations (BrainComposer / BodyComposer / PerceiveComposer / TeamComposer) — 包装 spawn.py 现有工厂调用（PR-5a 临时路径）。

**PR-5b / PR-12 待落地**：sub-composer 完全 self-contained（不再 import spawn.py 内部函数）；runtime 集成（mount/unmount 调用 ArtifactController + Composer）；TEAM composer 完整实现（TeamGraph 编排）。

Keeps: [ADR-0005](0005-composition-root-l4.md)、[ADR-0056](0056-plugin-group-contribution.md)、[ADR-0061](0061-plugin-manifest-resolve-boot.md)

> **核心决策：`spawn_agent` 是组合根门面，不持有装配策略。装配策略由 4 个 sub-composer plugin 承担，每个对应一个认知概念群；Brain/Body/Perceive/Team 各自的「如何连线」从 `spawn.py` 收敛到对应 sub-composer。**

## 背景

`lca/layer4_app/spawn.py` 现行 635 行，承担 L4 组合根的全部职责：`require_capability` 30+ 次，factory 调用 15+ 次，跨概念群内联装配策略若干。`composer.py` / `capability_boot.py` / `team_wiring.py` 在 PR-Phase-C 已内联进 `spawn.py`（注释自承 line 488 与 line 513）。

具体摩擦：

- `_apply_lead_brain`（line 247–256）是全仓库唯一一处伸手进 Brain 内部（`brain.reasoner` / `brain.critic` / `brain.skill_router` / `brain.agent_gates`）的地方——其他模块按 Brain Protocol 边界访问。
- `_resolve_brain`（line 283–304）硬编码 BrainFactory 位置参数（`llm, profile, tools_desc, tools, available_skills`）；BrainFactory Protocol 新增参数时（[ADR-0005](0005-composition-root-l4.md) 强制所有参数显式声明）需要同时改 `_resolve_brain`。
- `build_perceive_hub`（line 207–233）手动解析 `journal_store` + `perceive` service + `skill_store`，调用 `service.assemble(memory, store=..., skill_store=..., team=...)`——assemble 逻辑应该在 service 内（ADR-0056）而非 spawn 内。
- `spawn_team`（line 572–635）63 行编排手动解析 members、build stage、resolve lead、build strategy、build trace profile。

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

- `brain_composer.py`：`BrainComposer.compose_agent` 实现 `_resolve_brain` + `_apply_lead_brain` 的策略；持有 BrainFactory 协议调用方式与 lead 构造模板。
- `body_composer.py`：`BodyComposer.compose_agent` 实现 tool registry / safe executor / action registry / transport registry 的连线。
- `perceive_composer.py`：`PerceiveComposer.compose_agent` 实现 `build_perceive_hub` 的策略；调 `service.assemble()` 但参数选择在此层。
- `team_composer.py`：`TeamComposer.compose_team` 实现 `spawn_team` 的 63 行编排。

每个 sub-composer 是 cordis plugin，**boot 时通过 `ctx.provide("composer.brain", BrainComposer())` 注入**。`spawn.py` 通过 `require_capability(scope, "composer.brain")` 等 4 个 key 解析。

**`spawn_agent` 收缩。**

```python
async def spawn_agent(spec: AgentSpec, *, scope: Context | None = None) -> CognitiveAgent:
    scope = _ensure_scope(scope)
    composers = {name: require_capability(scope, f"composer.{name}") for name in ("brain", "body", "perceive")}
    graph = AgentGraph.merge(
        composers["brain"].compose_agent(spec, scope),
        composers["body"].compose_agent(spec, scope),
        composers["perceive"].compose_agent(spec, scope),
    )
    runtime = build_cognitive_runtime(graph.to_runtime_deps())
    return CognitiveAgent(runtime, spec.profile, graph.observability,
                          max_steps=spec.max_steps,
                          max_wall_clock_seconds=spec.max_wall_clock_seconds)
```

`_apply_lead_brain`（line 247–256）整体移入 `BrainComposer.compose_lead`，spawn 不再访问 Brain 内部字段。`build_perceive_hub` 整体移入 `PerceiveComposer`。

**Profile 化。** 默认 profile 装 4 个标准 sub-composer；科研 profile 可装自定义 `ResearcherBrainComposer`（保留 BrainFactory 协议约束）。

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| ADR-0005 兑现 | L4 组合根 = 组装门面；装配策略 = plugin | spawn.py 需重写，635 → ~200 行 |
| 测试 | sub-composer 单元测试用最小 scope（只注入需要的 capability） | 需新增 `tests/test_composer_*.py` 4 个文件 |
| 替换 | 换 Brain 装配策略 = 换 BrainComposer plugin | BrainFactory Protocol 签名扩展要求 4 个 sub-composer 同步更新 |
| Lead 构造 | `_apply_lead_brain` 从 spawn 移入 BrainComposer；Brain 内部字段封装 | 触及 BrainProtocol 的读取约定 |

**验证约束：**

- `tests/test_layer_boundary.py` 断言 L4 import 不下沉 L0/L1
- `tests/test_refactor_guards.py` 新增断言 `spawn.py` ≤250 行
- 4 个 sub-composer 各自单测；`spawn_agent` 测试降级为「解析 + 委派 + 返回 graph」
- 删 `_apply_lead_brain` 单测（如存在）；Brain 内部字段封装由 Brain Protocol test 覆盖

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 把 `spawn.py` 拆成多个文件但不引入 Protocol | 复制今日硬编码装配模式，违反 ADR-0005 与 plugin-everything |
| 把装配策略推回 group service（让 `BrainService.assemble` 自己构造 Brain） | 模糊群贡献（ADR-0056）与装配策略的边界；group service 应只负责 membership 与 default |
| 保留 `_apply_lead_brain` 作为 spawn 内部辅助 | 违反 Brain Protocol 封装；任何 Brain 内部字段重命名都强制改 spawn |
| 把 spawn 改成完全 YAML 驱动 | 等价于 sub-composer 由 profile YAML 选择；可在 Phase B 实现，本 ADR 不阻塞 |