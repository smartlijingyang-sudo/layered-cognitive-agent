# ADR-0066–0069 最终切换说明

> **状态：已切换。** Gateway 只负责 Profile 生命周期、HTTP/SSE 载体与每次 run 的调度；它不再拥有 Agent 对象装配、历史 Spawn 回退或 Creator 动作别名。

## 唯一运行路径

一次 `POST /runs` 经 Gateway 归一化输入并创建 `RunSession` 后，Loop Driver 使用已启动 Profile 的上下文构造 `AgentSpec` 或 `TeamSpec`。L4 `spawn` 必须取得 `CompiledRunPlan`，而 `bind_plan` 以完整 Composer 集合闭合 `AgentGraph` 或 `TeamGraph`。认知运行时只消费已闭合的 Brain、Body、Perceive、State、Hook、Stop 和 Observability 对象，不再自行选择历史装配分支。

| 架构层 | 唯一职责 | 禁止职责 |
|---|---|---|
| Gateway | 启动 Profile、接收 runs、建立 Session、调度 Driver、投射 SSE | 内联 Agent 组装、计划兼容开关 |
| Profile / PlanCompiler | 解析 bundle、投影 capability/control/scope、产生 `CompiledRunPlan` | 在请求期返回未编译配置 |
| L4 Spawn / bind_plan | 严格绑定完整 Composer 集合、闭合 Agent/Team 图 | legacy Spawn、缺失 Composer 的静默回退 |
| CognitiveRuntime | 执行闭合图、记录 Journal 事实 | 根据字符串重新装配组件 |
| CreatorRuntime | `inspect → author → validate → promote` Artifact 生命周期 | `mount`、`unmount`、`stage`、`retire`、`publish` 动作别名 |

## Artifact 与 Creator

Capability Artifact 只有 `DRAFT`、`VERIFIED`、`ACTIVE` 与 `RETIRED` 四种状态。`author` 加载源代码并创建 DRAFT；`validate` 执行 DRAFT → VERIFIED；`promote` 在 Composer 的 capability、metadata 与 invariant 检查成功后执行 VERIFIED → ACTIVE；`rollback=true` 执行 ACTIVE → RETIRED。`target_scope=release` 是 promote 的参数，不是独立 publish 动作；其副作用由 `PresetAuthoring` 写出 preset bundle。

| Creator face | 前置状态 | 后置状态 | 运行时效果 |
|---|---|---|---|
| `inspect` | 任意 | 不变 | 读取当前 Composer 图与已知 Artifact |
| `author` | 无 | `DRAFT` | 加载源、提取 factory 与 metadata |
| `validate` | `DRAFT` | `VERIFIED` | 验证 source、metadata 与 factory |
| `promote` | `VERIFIED` | `ACTIVE` | 内部调用 Composer mount；release 时写 preset |
| `promote(rollback=true)` | `ACTIVE` | `RETIRED` | 内部调用 Composer unmount |

## 关闭的旧入口

架构守卫会拒绝以下符号重新进入生产代码：`LCA_PLAN_COMPAT`、`use_legacy_spawn`、`legacy_sub_composers`、`legacy_state`、`migrate_legacy_state`、`LEGACY_TO_NEW_STATE`、`dispatch_legacy_action`、`actions_mount` 与 `actions_simple`。Creator Tool 的可用动作词表被固定为 `inspect`、`author`、`validate`、`promote`。

## 验证

最终切换由以下测试共同证明：计划绑定严格性、计划编译唯一性、四状态 property tests、Creator 四面闭集、Creator 端到端发布/复用/审计，以及生产源码零兼容符号扫描。任何新增替代流程必须先修改 ADR 与本说明，再扩展 `CompiledRunPlan` 或 Creator face；不得通过参数开关恢复第二条路径。
