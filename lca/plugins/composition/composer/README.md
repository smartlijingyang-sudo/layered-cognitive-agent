# composition/composer

Canonical home for plan-bound Agent assembly (migrated from `plugins/composer/`).

Legacy imports remain via COMPAT shims under `lca.plugins.composer`.
## 1. 职责

plan-bound Agent 装配的正式位置（自 `plugins/composer/` 迁入）：把已编译的
`CompiledRunPlan` / `V2ExecutablePlan` 与 profile 解析结果组装成可运行的
Agent 图，并向 registry 注册所需的 capability provider。

## 2. 不负责

- Profile / Bundle 解析与 plan 编译（`lca/harness/profile/`、
  `lca_kernel/plan/plan_compile.py`）
- run 期调度与 phase 遍历（`lca/loop/`、`lca/framework/graph/`）
- 副作用执行（Body / SafeExecutor 窄门，C10）

## 7. 副作用

装配期注册，run 期只读：`setup()` 经 `PluginContext` 的 provide / require /
register 声明（未声明调用触发 `UndeclaredInteractionError`）构造对象图；
不写文件、不写 Session、不改控制面 State。

`lca.plugins.composer` 下的 COMPAT shim 只做 import 兼容，不承载逻辑。
