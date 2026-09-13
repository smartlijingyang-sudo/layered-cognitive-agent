# 新人向：外环图怎么读 + act 如何调到工具

面向第一次摸 `phase_main_outer.yaml` / `act.yaml` 的工程师。
目标：会查类、会跟调用栈、不拿节点 id / `@plugin id` 当契约键。

权威驱动缝（生产单轨）：`DeclarativeExecution` → `PlanInterpreter` + `BundleGraphSpec`（ADR-0217/0218/0220）。
禁第二 Runtime：`NodeGraphDriver` / `GraphAssembler` / 平行 `GraphRuntime`。

---

## 1. 怎么读 YAML（查类口诀）

| 你在 yaml 里看到 | 含义 | 怎么落到代码 |
|---|---|---|
| `sub_spec_ref.plan_ref` | 外层节点无独立 Executor；递归进子图 | `PlanInterpreter` → `SubgraphStrategy` |
| `factory: foo.bar` | **业务语义名** = `semantic_name` | `rg 'semantic_name: str = "foo.bar"'` 或 `rg 'provides=.*::foo.bar'` |
| Cordis 键 | `{region}::{factory}` | 例：`concept::act.validate`、`phase:think::think.shortcut` |
| `@plugin id=...` | Cordis 插件身份，**不是**解析键 | 别用它接线；审 diff 用它当接线 → Reject |
| 节点 `id:` | 仅拓扑锚点（edges / journal） | **不是**契约键；测/审别钉节点 id |

叶子节点一定有 `factory`；带 `.ref` 且配了 `sub_spec_ref` 的节点通常只做委托，没有本层 Executor。

---

## 2. 外环总览（`bundles/phase_main_outer.yaml`）

驱动入口：`DeclarativeExecution` 跑 plan `phase.main.outer`。

```
perceive.main → think.main → act.main → reflect.main → remember.main → stop.main
     ↑                                                              │
     └──────────── stop 若 not should_stop 回环 ─────────────────────┘
```

各相可经 `should_stop` / `error` 短路进 `stop.main`。

六个 outer 节点都是 `sub_spec_ref`，没有本层 `factory`：

| outer 节点 | 子图 | entry | 叶子 factory → 类（路径） |
|---|---|---|---|
| `perceive.main` | perceive 子图 | `phase.perceive.observe` | `observe`→`PerceiveObserveExecutor`；`fold`→`PerceiveFoldExecutor`（`lca/plugins/loop/phase/perceive/*/plugin.py`） |
| `think.main` | `think.yaml` | `think.shortcut` | `shortcut`→`ThinkShortcutExecutor`；`route`→`ThinkRouteExecutor`；`reason`→子图 `think_reason`；`classify.ref` / `gate.ref`→decision 子图 |
| `act.main` | `act.yaml` | `act.validate` | 见下文 §3–§5 |
| `reflect.main` | reflect 子图 | `phase.reflect.score` | `score`→`ReflectScoreExecutor`；`admit_recovery`→`ReflectAdmitRecoveryExecutor` |
| `remember.main` | remember 子图 | `phase.remember.write` | `write`→`RememberWriteExecutor`；`fold`→`RememberFoldExecutor` |
| `stop.main` | stop 子图 | `phase.stop.should_check` | `should_check`→`StopShouldCheckExecutor`；`focus`→`StopFocusExecutor` |

### think.reason 内环（工具面入口，非 act）

`bundles/think_reason.yaml`：`fork_tools` → `plan` / `render` → 汇合 `complete`。

- `PromptReasoner` **不在图上**：Cordis boot 注入 `llm` / `selector` / `template_provider`；`complete_turn(..., tools)` 必传 `ForkedTools`。
- 沙箱工具可见性：`think.reason.fork_tools` → `ForkedTools`；声明了 sandbox 却缺 `runCommand`/`executeCode` → fail-loud（ADR-0222）。

测侧不变式优先盯：`ForkedTools` 可见集、`complete_turn` 必带 tools、journal EP、`broken_hop is None`。  
`FU-retire-v1-planinterpreter-tool-hop` 负责钉死 PlanInterpreter 驱动的真实工具 hop。

---

## 3. act 子图节点职责（`bundles/act.yaml`）

拓扑（全部 `when: true`，顺序硬编码）：

```
act.validate → act.authorize → act.envelope → act.dispatch → act.observe
```

| 节点 id | factory | 类 | 端口 | 做什么 |
|---|---|---|---|---|
| `act.validate` | `act.validate` | `ActValidateExecutor` | in/out: `decision` | Decision shape：`action_type` 闭集；`USE_TOOL` 要求 `tool_calls` 非空且有 `tool_name`；`DELEGATE`/`HANDOFF` 要求 `delegations` |
| `act.authorize` | `act.authorize` | `ActAuthorizeExecutor` | in: `decision`（state 可选） | 策略授权：budget（steps/tokens/cost）；USE_TOOL 的 call_id 唯一；危险 tool_name 本地拒 |
| `act.envelope` | `act.envelope` | `ActEnvelopeExecutor` | in: `decision` → out: `envelope` | `mint_envelope(...)`：`operation=body.act`，`grant.capability=body.act`，`effect_class=tools`，metadata 塞入 `state`+`decision` |
| `act.dispatch` | `act.dispatch.ref` | **无本层 Executor** | in: `envelope` → out: `receipt` | `sub_spec_ref` → `bundles/concept/effect_execute.yaml` entry `effect.execute` |
| `act.observe` | `act.observe` | `ActObserveExecutor` | in/out: `receipt` | 校验 `EffectReceipt`；写 `RunFact`；emit `phase.tool.call.end` / `phase.act.fold.end` |

源码目录：

- `lca/plugins/concept/act_subgraph/{validate,authorize,envelope,observe}.py`
- `lca/plugins/concept/effect_execute/execute.py`（`EffectExecuteExecutor`，`semantic_name="effect.execute"`）

`act.dispatch` 的 journal 括号：`emit_on_enter: body.tool.execute.start` / `emit_on_exit: body.tool.execute.end`（图级 EP，与 Body 内 `UseToolOperation` 发的同名 EP 可按 `decision_id` join）。

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
       │     mint_envelope(..., metadata.operation="body.act", decision, state)
       ├─ [act.dispatch.ref] → SubgraphStrategy(effect_execute.yaml)
       │     EffectExecuteExecutor.node_execute
       │       └─ runtime.effect_gateway.execute(envelope, policy)
       │            = RegistryEffectDispatcher.execute
       └─ ActObserveExecutor.node_execute(EffectReceipt)
```

关键文件：

- `lca/harness/declarative/execute/dispatch.py` → `RegistryEffectDispatcher`
- `lca/plugins/concept/effect_execute/execute.py` → 从 `context.runtime.effect_gateway` 取网关；缺失 → `RuntimeError`（fail-loud）

### 4.2 效果网关 → Body

```
RegistryEffectDispatcher.execute(envelope, policy)
  ├─ 校验 effect_class / approval / idempotency cache
  ├─ operation = envelope.metadata["operation"]   # "body.act"
  ├─ handler = EffectHandlerRegistry.resolve("body.act")
  └─ BodyActEffectHandler.handle(envelope, policy, capabilities)
        state    = metadata["state"]
        decision = metadata["decision"]
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

