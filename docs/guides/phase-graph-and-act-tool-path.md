# 新人向：外环图怎么读 + act 如何调到工具

面向第一次摸 `bundles/outer/phase_main.yaml` / act 子图的工程师。
目标：会查类、会跟调用栈、不拿节点 id / `@plugin id` 当契约键。

权威驱动缝（生产单轨）：`DeclarativeExecution` → `PlanInterpreter` + `BundleGraphSpec`（ADR-0217/0218/0220）。
禁第二 Runtime：`NodeGraphDriver` / `GraphAssembler` / 平行 `GraphRuntime`。

---

## 1. 怎么读 YAML（查类口诀）

| 你在 yaml 里看到 | 含义 | 怎么落到代码 |
|---|---|---|
| `sub_spec_ref.plan_ref` | 外层节点无独立 Executor；递归进子图 | `PlanInterpreter` → `SubgraphStrategy` |
| `factory: foo.bar` | **业务语义名** = `semantic_name` | `rg 'semantic_name: str = "foo.bar"'` 或 `rg 'provides=.*::foo.bar'` |
| Cordis 键 | `{region}::{factory}` | 例：`act::act.validate`、`think::think.shortcut`（region 取 executor 声明的 `region`，与 factory 未必同名） |
| `@plugin id=...` | Cordis 插件身份，**不是**解析键 | 别用它接线；审 diff 用它当接线 → Reject |
| 节点 `id:` | 仅拓扑锚点（edges / journal） | **不是**契约键；测/审别钉节点 id |

叶子节点一定有 `factory`；带 `.ref` 且配了 `sub_spec_ref` 的节点通常只做委托，没有本层 Executor。

---

## 2. 外环总览（`bundles/outer/phase_main.yaml` — M1 edge SSOT）

驱动入口：`DeclarativeExecution` 跑 plan `phase.main.outer`。
生产只认 `terminal.commit` + 本文件；旧名 `stop.main` / `phase_main_outer.yaml` 已退役。

```
perceive.main → think.main → act.main → reflect.main → remember.main → terminal.commit
                     ↑                      │
                     └── admit_recovery（有界）─┘
```

- think / act 可经 decision / should_terminate 短路进 `terminal.commit`。
- reflect→think recovery：`routing.next_hint == admit_recovery` + `loop.maxIterations: 1`（缺边 = 编译失败）。
- 故障域义务附件：`docs/architecture/phase-graph-node-orchestration/04-m1-fault-domain-obligations.md`。

六个 outer 节点（除 terminal）都是 `sub_spec_ref`，没有本层 `factory`：

| outer 节点 | 子图 | entry | 叶子 factory → 类（路径） |
|---|---|---|---|
| `perceive.main` | perceive 子图 | `phase.perceive.observe` | `observe`→`PerceiveObserveExecutor`；`fold`→`PerceiveFoldExecutor` |
| `think.main` | think 子图 | `think.shortcut` | `shortcut` / `route` / `reason` / decision classify+gate |
| `act.main` | act 子图 | `act.validate` | 见下文 §3–§5 |
| `reflect.main` | reflect 子图 | `phase.reflect.score` | `score`→`ReflectScoreExecutor`；`admit_recovery`→`ReflectAdmitRecoveryExecutor` |
| `remember.main` | remember 子图 | `phase.remember.write` | `write`→`RememberWriteExecutor` |
| `terminal.commit` | （本层 binding: terminate） | — | `TerminateStrategy` → `terminal_outcome` |

### think.reason 内环（工具面入口，非 act）

`bundles/think_reason.yaml`：`fork_tools` → `plan` / `render` → 汇合 `complete`。

- `PromptReasoner` **不在图上**：Cordis boot 注入 `llm` / `selector` / `template_provider`；`complete_turn(..., tools)` 必传 `ForkedTools`。
- 沙箱工具可见性：`think.reason.fork_tools` → `ForkedTools`；声明了 sandbox 却缺 `runCommand`/`executeCode` → fail-loud（ADR-0222）。

测侧不变式优先盯：`ForkedTools` 可见集、`complete_turn` 必带 tools、journal EP、`broken_hop is None`。  
`FU-retire-v1-planinterpreter-tool-hop` 负责钉死 PlanInterpreter 驱动的真实工具 hop。

---

## 3. act 子图节点职责（`bundles/act/act_subgraph.yaml`）

拓扑（主路径顺序硬编码；三条边为 `when:` 谓词路由，见下）：

```
act.validate → act.authorize → act.approve.gate → act.envelope → act.fanout
  → effect.pre_dispatch.envelope_check → act.dispatch → act.join
  → act.observe.normalize → act.observe.commit_fact → act.observe.terminate_decide
```

- `act.approve.gate`：仅当 `approval_routing.next_hint ∈ {approve_skipped, approve_approved}` 前进；interrupt / rejected 无内边（ADR-0237/ADR-0292）。
- `act.fanout`：1:1 分发（`routing.next_hint == fanout_1to1`）时才进 `effect.pre_dispatch.envelope_check`（ADR-0234 5-gate 校验，产 `verdict_refs` typed port）。
- `act.join`：收敛 `receipts` 列表；`routing.next_hint == join_1to1` 时进 observe 三件套。

| 节点 id | factory | 类 | 端口 | 做什么 |
|---|---|---|---|---|
| `act.validate` | `act.validate` | `ActValidateExecutor` | in/out: `decision` | Decision shape：`action_type` 闭集；`USE_TOOL` 要求 `tool_calls` 非空且有 `tool_name`；`DELEGATE`/`HANDOFF` 要求 `delegations` |
| `act.authorize` | `act.authorize` | `ActAuthorizeExecutor` | in: `decision`（state 可选） | 策略授权：budget（steps/tokens/cost）；USE_TOOL 的 call_id 唯一；危险 tool_name 本地拒 |
| `act.approve.gate` | `act.approve.gate` | — | in: `approval_requirement` | 审批门（ADR-0237/ADR-0292）：`approve_skipped`/`approve_approved` 前进，其余 verdict 无内边 |
| `act.envelope` | `act.envelope` | `ActEnvelopeExecutor` | in: `decision`, `state` → out: `envelope` + 透传 `decision`, `state` | `mint_envelope(...)`：`operation=body.act`，`grant.capability=body.act`，`effect_class=tools`；`metadata` 经 `ToolsEnvelopeMeta` 类型化构造，**活对象（`state`/`decision`）不再塞入**（RA-033 杀死了旧 metadata 偷渡） |
| `act.fanout` | `act.fanout` | — | in: `envelope` → out: `envelope`, `envelopes`, `routing` | 1:1 envelope 分发边界节点（PR-3.8.4） |
| `effect.pre_dispatch.envelope_check` | `effect.pre_dispatch.envelope_check` | — | in: `envelope` → out: `envelope`, `verdict_refs` | 5-gate 原子校验（ADR-0234）；`verdict_refs` typed port 供 `act.dispatch` / `effect.execute` |
| `act.dispatch` | `act.dispatch.ref` | **无本层 Executor** | in: `envelope`, `verdict_refs`, `decision`, `state` → out: `receipt` | `sub_spec_ref` → `bundles/concept/effect/effect_execute.yaml` entry `effect.execute`（`state`/`decision` typed port 转发，ADR-0235） |
| `act.join` | `act.join` | — | in: `receipts` → out: `receipt`, `routing` | 收敛 `receipts`（`effect.execute` 发 list-of-one）；`join_1to1` 路由进 observe |
| `act.observe.normalize` | `act.observe.normalize` | `ActObserveExecutor` | in: `receipt` | 校验 `EffectReceipt` 并归一化；emit `phase.tool.call.end` / `phase.act.fold.end` |
| `act.observe.commit_fact` | `act.observe.commit_fact` | — | — | observation-plane RunFact 落库 |
| `act.observe.terminate_decide` | `act.observe.terminate_decide` | — | — | should_terminate 路由决策（PR-3 三件套分工：normalize / commit_fact / terminate_decide） |

源码目录：

- `lca/nodes/act/{validate,authorize,envelope,observe}/`（`Act*Executor`，`region="act"`，composite key 为 `act::<semantic_name>`）
- `lca/nodes/concept/effect/execute.py`（`EffectExecuteExecutor`，`semantic_name="effect.execute"`）

`act.dispatch` 当前 `emit_on_enter`/`emit_on_exit` 皆为空——`body.tool.execute.start` 的发射器已移到 session emit 面（`lca/infrastructure/session/emit/cognitive_emit/tool_events.py`），别再按旧 journal 括号查。

---

## 4. act → 工具：完整代码调用栈

以 `action_type=use_tool` 为例（最常见工具路径）。

### 4.1 图内（声明式）

```
PlanInterpreter
  └─ SubgraphStrategy(act.yaml)
       ├─ ActValidateExecutor.node_execute
       ├─ ActAuthorizeExecutor.node_execute
       ├─ ActEnvelopeExecutor.node_execute
       │     mint_envelope(..., operation="body.act", via ToolsEnvelopeMeta)  # decision/state 走 typed port，不再进 metadata
       ├─ [act.dispatch.ref] → SubgraphStrategy(effect_execute.yaml)
       │     EffectExecuteExecutor.node_execute
       │       ├─ state = typed port ?? context.runtime.state（AgentState isinstance 守卫；真实 run 里 port 未接线，todo-80）
       │       └─ runtime.effect_gateway.execute(envelope, policy, state=..., decision=active_decision)
       │            = RegistryEffectDispatcher.execute  # active_decision = 显式决策 or 构造注入 self._decision
       └─ act.join → act.observe.normalize / commit_fact / terminate_decide(EffectReceipt)
```

关键文件：

- `lca/harness/declarative/execute/dispatch.py` → `RegistryEffectDispatcher`
- `lca/nodes/concept/effect/execute.py` → 从 `context.runtime.effect_gateway` 取网关；缺失 → `RuntimeError`（fail-loud）；state typed port 为 None 时回退 `context.runtime.state`（todo-80）

### 4.2 效果网关 → Body

```
RegistryEffectDispatcher.execute(envelope, policy, *, state=None, decision=None)   # ADR-0235
  ├─ 校验 effect_class / approval / idempotency cache
  ├─ operation = envelope.metadata["operation"]   # "body.act"
  ├─ handler = EffectHandlerRegistry.resolve("body.act")
  ├─ active_decision = decision if decision is not None else self._decision   # RA-043
  ├─ active_state = state if state is not None else self._state                # RA-043：构造捕获值同样转发
  └─ BodyActEffectHandler.handle(envelope, policy, capabilities, state=active_state, decision=active_decision)
        # state / decision 走 typed kwargs；为 None → PG-003 fail-loud（RA-033）
        return await capabilities.body.act(decision, state)
```

Handler 注册：`lca/plugins/act/effect/handlers_provider.py`（`BodyActEffectHandler`，`receipt_name="body.acted"`）。

### 4.3 Body → Action → SafeExecutor → Tool

```
SimpleBody.act(decision, state)                    # lca/cognition/body/executor/simple_body.py
  ├─ cursor advance → phase "act"（USE_TOOL）
  ├─ record_decision_made
  └─ action_registry.resolve(decision.action_type)  # "use_tool"
        └─ UseToolOperation.execute                 # action_handlers.py
              ├─ tool_wire_block_observation（incomplete/invalid → 不执行，回 Observation）
              ├─ commit_body_tool_decision_start/end
              └─ ToolBatchExecutor.execute(tool_calls)
                    ├─ ToolRegistry 解析 tool_name（含 snake_case→camelCase：run_command→runCommand）
                    ├─ 批调度（串/并段）
                    └─ SimpleSafeExecutor.execute(tool, args, ...)
                          ├─ permission_manifest.allowed_tools
                          ├─ schema 校验 args
                          ├─ record_step_tool_call / ToolStarted
                          ├─ body.sandbox.enter
                          ├─ tool_invocation_scope(invocation_id)
                          ├─ _execute_with_retry → await tool.execute(args)   # ★ 世界副作用叶子
                          ├─ body.sandbox.exit
                          └─ ToolInvoked / Observation
```

叶子：`tool.execute(args)` 才是真正碰沙箱 / 文件系统 / 外部 IO 的点。  
沙箱工具（`runCommand` / `executeCode`）由 agent 配置 + tools provider 注册进 `ToolRegistry`；think 侧可见性靠 `ForkedTools`，act 侧执行靠 Body 这条链——**两套面**：模型看见 vs Body 执行。

非 `use_tool`：`SimpleBody` 仍走同一 `action_registry`，只是 handler 换成 `DelegateOperation` / `Respond` / `Stop` 等；`act.envelope` 仍打 `operation=body.act`，世界效应仍经同一 `effect_gateway`。

### 4.4 回程类型

```
Observation
  → BodyActEffectHandler 返回
  → RegistryEffectDispatcher 包成 idempotency receipt（若有 key）
  → EffectExecuteExecutor 折成 EffectReceipt(outcome=SUCCEEDED|FAILED, ...)
  → act.observe 写入 RunFact / 透传 receipt
```

---

## 5. 两张图对照（别混）

| 层 | 真值 / 边界 DTO | 副作用写在哪 |
|---|---|---|
| 图节点 | `Decision` → `CommandEnvelope` → `EffectReceipt` | 节点本身不直接 `tool.execute`；dispatch 委托 gateway |
| Body 平面 | `Decision` → `Observation` | `SafeExecutor` → `tool.execute` |
| Think 工具面 | `ForkedTools` 进 `complete_turn` | **不执行**工具；只让 LLM 看见可调工具集 |

`CommandEnvelope` 是声明式执行链唯一的效果授权入口（`SimpleBody` 文档不变量）；Body **不再**私造旧 `ExecutionEnvelope`。

---

## 6. 新人调试清单

1. 断点优先打：`ActEnvelopeExecutor.node_execute` → `RegistryEffectDispatcher.execute` → `BodyActEffectHandler.handle` → `UseToolOperation.execute` → `SimpleSafeExecutor._execute_with_retry`。
2. `effect_gateway is None` → boot 没挂 `RegistryEffectDispatcher`，不是 yaml 写错节点 id。
3. `undeclared effect operation: body.act` → EffectHandler provider 没装进 profile。
4. `工具 X 未在 ToolPermissionManifest.allowed_tools` → 权限面，不是图拓扑。
5. think 看不到 `runCommand` → 查 `fork_tools` / sandbox 绑定（P2），不是 act 节点。
6. 查类永远：`factory` / `semantic_name`；契约断言永远别钉节点 id。

---

## 7. 相关 ADR / 跟进

- ADR-0217 Bundle Graph Schema v2  
- ADR-0218 Bundle Graph v2 subgraph driver  
- ADR-0220 Three-tier graph + boundary typing  
- ADR-0222 Retire v1 / Reasoner SRP / sandbox ForkedTools fail-loud  
- Follow-up：`FU-retire-v1-planinterpreter-tool-hop`（PlanInterpreter 驱动真实工具 hop 契约测）

