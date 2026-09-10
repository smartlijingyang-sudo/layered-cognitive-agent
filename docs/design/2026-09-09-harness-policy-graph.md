# Harness Policy Graph — 复用于 Think / Act / Reflect 的控制面子图

> Status: proposed. Awaits review before any contract change. delete-when:
> superseded by the eventual ADR (proposed/accepted) that promotes this
> design into a binding decision. Companion to brainstorming chat.

## 1. 问题与目标

业务阶段图 (`CognitivePhaseGraphPlan`) 只负责"下一步做什么"；模型调用、
工具调用、记忆查询都落在 Think / Act / Reflect 节点上。但这些节点今天仍
要各自决定：

- 重复工具 / 重复 prompt 是否应被拒;
- 预算与 token / 调用次数 / 阶段访问次数如何收紧;
- 模型幻觉、低证据、不一致观察的判定与回退路径;
- Act 中"工具可能已执行但结果未知"时如何避免自动重试;
- 失败分类 (deterministic / transient / uncertain) 如何映射到控制动作.

这些是**模型控制面**问题，不是业务任务流。当前实现把策略散落在多个
`phase.execution_policy.*` provider 与若干 `control.*.plugin` 中,缺少统
一的拓扑载体与声明方式,新增控制规则往往意味着修改多个 plugin 而不是
扩展 profile。

### 1.1 目标

- 把可复用的控制规则(重复检测、预算门、失败分类、恢复边)收敛为一个有
  版本的小图 (`Harness Policy Graph`)。
- 业务节点只需声明应用点与输入/输出映射,不直接拼策略列表。
- 同一拓扑可复用于 Think / Act / Reflect,差异由 operation 绑定与策略参
  数决定。
- 与现有 `sub_spec_ref` / `subgraph_ref` 共用编译与递归基础,但语义边
  界清晰:业务子图 vs 控制面子图。

### 1.2 非目标

- 不引入第七个认知阶段或新的 EXECUTION_POINTS 事件词表。
- 不让 Policy Graph 直接执行模型或工具;副作用仍走
  `Body → SafeExecutor → Effect Gateway`。
- 不让 Policy Graph 绕过 Reducer 写 `AgentState`。
- 不为模型幻觉检测、prompt injection 检测做完整的产品方案;第一版只
  提供 typed `PolicyFinding` 与 verdict 投影。
- 不替代现有 `phase.execution_policy.resilient` 的 timeout/retry 语
  义;两者各管一段(执行弹性 vs 控制流判定)。

## 2. 概念分层

```
+-----------------------------------------------+
|   Declarative Business Graph (Cognition)      |
|   - phase nodes (perceive/think/act/reflect)  |
|   - edges + subgraph_ref (业务子图)            |
|   - 每个节点可选 policy_ref (控制面 wrapper)   |
+-----------------------------------------------+
                       │
                       ▼ policy.application
+-----------------------------------------------+
|   Harness Policy Graph (Control Plane)        |
|   - view / guard / detector / gate            |
|   - delegate (受控 delegation boundary)       |
|   - observation classifier / failure policy   |
|   - verdict / hint / recovery / uncertain     |
+-----------------------------------------------+
                       │
                       ▼
+-----------------------------------------------+
|   Existing Execution Narrow Gate              |
|   PhaseExecutor / Model / Effect Gateway      |
+-----------------------------------------------+
```

业务图决定"做什么";Policy Graph 决定"是否允许做、如何约束、失败后如何
收敛";执行窄门仍然只有一条。任何 control plane 都不能绕过它写世界。

## 3. Contract 草案

新增四个 frozen dataclass + 一个应用层 entry,放在
`lca/contracts/protocols/declarative/declarative_1/policy_graph.py`,
与 `declarative_graph.py` 同层。所有字段 frozen、`extra="forbid"`,遵守
C13 信息血统闭合。

```python
@dataclass(frozen=True, slots=True)
class PolicyNode:
    id: str
    role: PolicyNodeRole           # view / guard / detector / gate
                                     # / delegate / classifier / failure_policy
                                     # / projection
    binding: str                    # capability key, 走现有 provider registry
    config: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolicyEdge:
    source: str
    target: str
    when: str                       # 与 PhaseEdge.when 同语义
                                    # (callable 名字字符串, harness 解析)


@dataclass(frozen=True, slots=True)
class PolicyGraphPlan:
    id: str                         # e.g. "harness.policy.model-call.v1"
    entry: str                      # policy.input
    nodes: tuple[PolicyNode, ...]
    edges: tuple[PolicyEdge, ...]
    contract_version: str = "harness.policy.evaluation.v1"

    def __post_init__(self) -> None:
        # PG-008: 入口 / 节点 / 边 / 闭合不变量
        ...


@dataclass(frozen=True, slots=True)
class PolicyApplication:
    graph_ref: str
    apply: str                      # "before" | "after" | "before_and_after"
    input_bindings: tuple[tuple[str, str], ...]
    operation: PolicyOperation
    output_bindings: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class PolicyOperation:
    capability: str                 # 例如 model.generate / effect.gateway
    command: str | None = None
    params: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolicyInput:
    phase: SemanticPhase
    node_id: str
    run_id: str
    invocation_id: str             # 每次 policy application 唯一,供重复检测
    context: Mapping[str, object]
    budget: BudgetSnapshot
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicyObservation:
    status: str                     # ok / error / uncertain
    evidence: tuple[str, ...] = ()  # 引用 RunFact / observation id
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyFinding:
    kind: str                       # e.g. "repeat_command", "unsupported_claim"
    confidence: float               # 0.0 ~ 1.0
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PolicyVerdict:
    kind: str                       # allow / deny / hint / recover
                                     # / uncertain_effect
    reason: str
    hint: str | None = None
    recovery_edge: str | None = None   # 必须由业务节点预声明
    uncertain_effect: bool = False
    findings: tuple[PolicyFinding, ...] = ()
```

`PolicyVerdict` 与现有词汇的关系:

| LCA 词汇      | 含义                       | Policy Verdict 关系 |
|---------------|----------------------------|---------------------|
| `Decision`    | cognition 候选意图         | 不重叠             |
| `Verdict`     | Gate/Policy 控制面许可      | **Policy Graph 是其生产者之一** |
| `EffectReceipt` | Body 副作用回执           | 不重叠             |
| `PolicyObservation` | 策略对执行的观察       | 中间态,不写入 State |

## 4. Policy Node 类型

| role          | 作用                                          | 例子                           |
|---------------|-----------------------------------------------|--------------------------------|
| `view`        | 构造只读策略上下文                             | `context_view`、`budget_view`  |
| `guard`       | 进入前许可                                     | `capability_guard`、`approval_guard` |
| `detector`    | 产生 `PolicyFinding`,不直接跳业务边          | `repeat_detector`、`hallucination_signal` |
| `gate`        | 综合 finding 与预算,产出 allow/deny           | `budget_gate`、`risk_gate`     |
| `delegate`    | 受控 delegation 到现有 executor / gateway     | `model.generate`、`effect.gateway` |
| `classifier`  | 对执行结果标准化分类                          | `timeout`、`deterministic_error` |
| `failure_policy` | 把分类结果映射成 verdict / recovery       | `retry_if_idempotent`、`recover_to_think` |
| `projection`  | 产出 verdict / hint / recovery / observation | `policy_evaluation`            |

关键原则:**detector ≠ gate ≠ failure_policy**。detector 只产生 finding,
gate 与 failure_policy 才产生控制动作。这样模型幻觉检测不会变成一个硬编
码 stop。

## 5. 节点声明与业务绑定

### 5.1 业务节点声明 policy_ref

```yaml
nodes:
  - id: think.model_call
    phase: think
    binding: phase.think.standard
    policy:
      graph_ref: harness.policy.model-call.v1
      apply: before_and_after
      input:
        prompt: input.prompt
        context: input.context
        prior_observations: state.observations
        budget: state.budget
      operation:
        capability: model.generate
      output:
        verdict: result.verdict
        hint: result.hint
        recovery: result.recovery
        observation: result.observation
```

Act 节点复用同一图但替换 operation:

```yaml
- id: act.tool_call
  phase: act
  binding: phase.act.standard
  policy:
    graph_ref: harness.policy.tool-call.v1
    operation:
      capability: effect.gateway
      command: input.command
```

### 5.2 Policy Graph 自身声明

```yaml
# bundles/policies/model-call.yaml
policy_graphs:
  - id: harness.policy.model-call.v1
    plan_ref: bundles/policies/model-call.yaml
    entry_node: policy.input
    rules:
      repeat_detector:
        key: semantic_prompt_hash
        window: current_think_visit
        on_repeat: hint_then_reenter
      budget_gate:
        budget: model.calls
        max: 8
      evidence:
        required: true
      hallucination_signal:
        on_detected: hint_then_reenter
      low_confidence:
        on_detected: recover_to_reflect
```

## 6. 编译不变量(新增代码段:PG-008 / PS-007)

| 代码    | 不变量 |
|---------|--------|
| PG-008  | `PolicyGraphPlan` 必须有入口节点;节点 ID 不重复;所有边端点存在;存在 terminal/deny/recovery 闭合;不允许无界循环;递归深度 ≤ `MAX_POLICY_GRAPH_DEPTH`(= 4)。 |
| PG-009  | `PolicyApplication.graph_ref` 必须能解析到声明的 `PolicyGraphPlan`;`apply` ∈ {before, after, before_and_after};`input_bindings` / `output_bindings` 字段必须为非空字符串对。 |
| PG-010  | `delegate` 节点的 binding 必须是已声明的模型/效果 capability,不允许 `effect.*` 之外的副作用能力。 |
| PS-007  | `PolicyVerdict.recovery_edge` 必须是宿主业务节点预先声明的允许边之一;不允许默认恢复。 |
| PS-008  | Act 的 `uncertain_effect=true` 不得连接到自动重试边;只能连接到 reconciliation 或 stop。 |
| PS-009  | deterministic error 不得配置为无限重试;transient 错误必须配 `idempotency_required` 字段。 |
| PS-010  | Policy Graph 产生的 observation / verdict 只能经投影写入 trace/evidence;不允许写 `AgentState`。 |

## 7. 运行时:before/after delegation runner

```
business node entry
  ↓
resolve policy.graph_ref
  ↓
construct PolicyInput
  ↓
run policy pre-delegation subgraph
  ↓
verdict.allow?
  ├─ no  → emit PolicyVerdict, return to business graph
  └─ yes
       ↓
     call existing PhaseExecutor / Model / Effect Gateway
       ↓
     construct PolicyObservation
       ↓
     run policy post-delegation subgraph
       ↓
     emit PolicyVerdict / recovery / hint / observation
       ↓
business graph selects next edge (recovery_edge only if pre-declared)
```

业务图只处理 Policy Graph 的标准结果,不知道其内部节点。Policy Graph 不
直接修改业务图游标,不允许偷偷跳转。

## 8. 失败 / 重试 / 恢复矩阵

| 情况                       | Think               | Act                                  | Reflect                |
|----------------------------|---------------------|--------------------------------------|------------------------|
| 重复模型调用               | hint / re-enter     | n/a                                  | hint / re-enter        |
| 重复工具调用               | n/a                 | deny / require_approval              | n/a                    |
| 预算耗尽                   | stop / recovery     | stop                                 | stop                   |
| deterministic error        | deny                | deny                                 | deny                   |
| transient 模型错误         | retry if budget     | n/a                                  | retry if budget        |
| 工具 timeout               | n/a                 | **uncertain_effect** / reconcile     | n/a                    |
| 低证据输出                 | recover / reflect   | n/a                                  | hint / think recovery  |
| 不一致观察                 | reflect recovery    | reconciliation                       | think recovery         |
| 能力不足                   | deny                | deny                                 | deny                   |

默认值必须显式声明,不靠解释器的隐藏 fallback。

## 9. 与 `sub_spec_ref` / `subgraph_ref` 的边界

| 维度            | 业务子图                         | Policy Graph |
|-----------------|----------------------------------|---------------|
| 角色            | 业务流程嵌套                     | 控制面 wrapper |
| 返回值          | 业务结果(可能含新事实/状态变化) | `PolicyVerdict` |
| 权限            | 完整 plan 权限                   | 仅控制面许可,不允许绕过执行窄门 |
| 嵌套规则        | PG-004 mutual reference          | PG-008 自包含,不引用业务子图 |
| 与 EXECUTION_POINTS | 可产生 spine 事件              | 不新增事件,只产生 control verdict |

底层可复用现有 `SubgraphResolver`、`GraphAssembler`、`MAX_SUBGRAPH_DEPTH`
限制;但上层 contract 必须明确区分两类图。

## 10. 第一版范围

```
1. PolicyGraphPlan / PolicyApplication / PolicyInput / PolicyVerdict /
   PolicyFinding / PolicyObservation frozen dataclass
2. PolicyGraph resolver + compiler (PG-008 / PG-009 不变量)
3. before/after delegation runner
4. allow / deny / hint / recover / uncertain_effect 五种 verdict
5. repeat detector / budget gate / failure classifier 三个内置 policy node
6. Act uncertain-effect 保护(PS-008)
7. 三个示例 policy graph: model-call / tool-call / reflect-summary
8. Think / Act / Reflect 集成测试
9. tests/contracts/test_policy_graph_contract.py
10. tests/harness/graph/execute/test_interpreter_policy.py
```

不在第一版范围:

- 模型幻觉检测的完整产品方案(只先提供 typed finding 接口)。
- 跨 invocation 的复杂关联(目前 `invocation_id` 单次 policy 应用唯一)。
- Policy Graph 的可视化 / 调试 UI。

## 11. 待决项

1. `PolicyVerdict.recovery_edge` 是否允许引用边级 `subgraph_ref`(嵌套)
   还是仅引用业务图节点?倾向:仅节点级,边级 subgraph_ref 留作下一版。
2. Policy Graph 节点之间能否并行?倾向:第一版顺序执行,提供 declared
   join 边;并行放后面。
3. Policy Graph 与现有 `phase.execution_policy.*` (timeout / retry) 的边
   界是否完全正交?倾向:正交,execution_policy 仍由内核负责 timeout /
   retry,Policy Graph 负责"是否允许重试"决策。
4. `PolicyInput.budget` 是从 `BudgetSnapshot` 还是 `RunBudget` 取?需要再
   与 ADR-0194/0195 runtime projection 对齐。

## 12. 与现有仓库规则的关系

- 不变量:C1(认知闭集)、C3(事实可追溯)、C4(Reducer 单写)、C5(能力单
  调)、C10(执行窄门)、C11(事件闭集)、C13(信息血统闭合)在本设计中全部
  保留,Policy Graph 不新增阶段、不新增事件、不绕执行窄门。
- 文档归属:本文档位于 `docs/design/`,与 `2026-09-09-edge-subgraph-ref-
  minimal-cut.md` 同目录;若被 ADR 接受则后续在 `docs/notes/implemented/
  contract/` 与 ADR 同步沉淀。
- 验证矩阵(与 AGENTS.md §6 对齐):
  - 普通 seam 实现:`ruff check` + `ruff format` + 相关 pytest。
  - contract 改动:全部实现 + 测试 + mypy。
  - 枚举 / 闭集改动:catalog / whitelist + 序列化兼容 + 重放测试。
  - Profile/Bundle 改动:plugin shape + resolve 测试 + DAG + 能力归属 +
    effects 审计。

## 13. 下一步

1. 在评审通过后,把本设计中的 contract 草案转写为 ADR (Proposed)。
2. ADR 接受后再写 Agent Note `docs/notes/proposed/contract/`,并按
   `lca-write-note` 的三行表头与替代方案要求落地。
3. 实现路径按第 10 节第一版范围分阶段切,每个阶段单独 PR,且每个 PR 同时
   闭合对应测试与文档。