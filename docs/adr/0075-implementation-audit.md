# ADR-0075 实施深度审计

> 审计日期：2026-08-22
>
> 审计目标：确认默认生产路径是否真正由 `CompiledRunPlan`、`PhaseGraph`、`GraphAssembler` 与 `GenericPlanInterpreter` 驱动，并识别任何仍会造成“双轨”或“空壳”风险的实现。

## 已确认的实质实现

| ADR-0075 要求 | 已确认实现 | 证据位置 |
|---|---|---|
| 单一 v2 运行计划 | `CompiledRunPlan` 同时携带 PluginSpec、bindings、图、替换、effect policy 与 validation report，并参与 plan hash。 | `lca/contracts/protocols/plan.py` |
| 默认 Profile 显式六阶段 | 标准 Profile 引入 `bundles/declarative-phase-graph.yaml`，每个 semantic phase 均有原生 `PluginSpec` 和 PhaseExecutor capability。 | `profiles/web-standard.yaml`、`lca/plugins/phase_executors/` |
| 通用编译与解释 | PlanCompiler 编译 declarative projection；GraphAssembler 按 capability binding 解析；GenericPlanInterpreter 推进 PhaseResult 和 graph edge。 | `lca/harness/declarative/` |
| 默认 Agent 装配接线 | Agent assembly 将 compiled plan 与 phase executor bindings 注入 CognitiveRuntime，运行时优先走 DeclarativeRuntimeDriver。 | `agent_assembly.py`、`runtime_loop.py`、`declarative_runtime.py` |
| 严格工具链 | `plugin check --strict`、`plan compile`、`plan validate`、`graph`、`explain plan` 与 `audit declarative-boundaries` 均已接入。 | `lca/layer0_infra/ops/commands/declarative.py` |

## 发现的必须补齐项

| 风险 | 当前表现 | ADR-0075 不符合点 | 补齐方向 |
|---|---|---|---|
| 旧 runtime 仍含固定调用 | `CognitiveRuntime._loop` 仍直接调用 brain/body/memory/stop；虽非默认 compiled path，却仍是生产代码 fallback。 | M3/M7、A12 禁止双轨。 | 将 fallback 限定为显式 legacy adapter 或删除固定调用，并令默认路径完全无业务阶段分派。 |
| act 绕过 Effect Gateway | 标准 act executor 在 direct body adapter 模式下直接调用 `body.act`。 | PG-003、A8。 | act 改为只 mint CommandEnvelope，由 runtime EffectGateway 执行受控 handler 并提交 receipt。 |
| remember 直接写记忆 | 标准 remember executor 直接调用 `memory.update`。 | PG-005、状态/效果边界。 | 产出受准入 WriteSet/CommandEnvelope，经 memory effect handler 执行并记录 receipt。 |
| Journal 证据未接入生产 committer | GenericPlanInterpreter 默认使用 in-memory committer。 | Journal 事实边界与 A8/A10 证据要求。 | 注入 runtime JournalCommitter，记录 phase fact、effect receipt 与 observation 的 plan/node provenance。 |
| 控制贡献未执行 | 新 graph 编译 control entries，但声明式运行路径尚未驱动 govern contribution DAG。 | M4、A5。 | 在执行器前/后按 PhaseBinding contribution role 调度，并使 verdict 聚合进入 PhaseResult。 |

结论：当前提交已经切入了新的默认声明式编译、装配和运行入口，但在 effect、memory、journal、control contribution 以及旧路径删除方面仍不能称为 ADR-0075 的完整落地。后续工作必须先补齐上述项目，再推送。

## 基础设施复用结论

现有 `CommandEnvelope` 已是世界效果的唯一入口，具备 `plan_ref`、`decision_ref`、provider、grant、预算保留、幂等键和 policy verdict 引用；声明式 `EffectGateway` 可直接以该契约作为入参。现有 observability facade 提供 `record(event)` 并在运行 scope 内路由到已绑定 Journal backend，因此新的 `JournalCommitter` 应生成带 plan/node provenance 的 JournalEvent 后经 facade 提交，而不能继续使用仅测试用途的内存列表。

这些基础设施足以支持在不新增第二套命令或日志协议的前提下补齐 act/remember 的受控效果路径；实现将把具体 body/memory 调用移动到 Runtime-owned Effect Gateway handler，PhaseExecutor 仅产出已记录 Decision 关联的 CommandEnvelope。

进一步确认：`PlanCompiler` 已从所有激活 `PluginSpec.effects` 汇总 `EffectPolicyPlan.allowed_effects`、approval 与 idempotency 要求。因此补齐后的 Runtime EffectGateway 无需引入平行策略来源，可直接对 envelope 的声明 effect class 与该编译产物实施 fail-closed 校验。

## 补齐结果与运行证据

本轮补齐已将标准 `act` 和 `remember` PhaseExecutor 改为仅 mint `CommandEnvelope`；`RuntimeEffectGateway` 现在是运行时内唯一调用 `body.act` 与 `memory.update` 的位置，并依据编译得到的 `EffectPolicyPlan` 强制 effect class、审批和幂等要求。`GenericPlanInterpreter` 将 effect receipt 作为阶段 artifact 写回，故 `reflect` 仅消费经网关执行并由 Journal 提交的 observation。

`RuntimeJournalCommitter` 已通过 observability 包根的 `record_runtime` 进入当前绑定 Journal backend；解释器为每次阶段执行提交含 plan/node provenance 的 `phase.result` 事实，并为 effect receipt 提交 Journal 记录。`GraphAssembler` 已解析每个 PhaseBinding 的 contribution executor；解释器实际执行 `prepare`、`govern`、`transform`、`observe` 与 `finalize` 角色，其中 govern 拒绝会 fail-closed。

新增真实默认 Profile 端到端测试在运行前将旧 `_loop` 替换为失败函数，Agent 仍成功完成任务，证明默认 boot → compose → run 已经通过 `CompiledRunPlan` → `GraphAssembler` → `GenericPlanInterpreter` → `RuntimeEffectGateway` 的新架构路径。核心验收集已通过 82 项测试；Ruff、Mypy、`plugin check --strict`、`plan validate` 与 `audit declarative-boundaries` 均通过。

旧 `_loop` 仍作为无 `CompiledRunPlan` 的历史直接构造测试适配路径保留；它不是默认 Profile 的可达路径。生产 Profile 通过显式六阶段 bindings 启动时，运行时不会执行该 fallback。

## Task 5-8 最终验收（2026-08-22）

Task 5-8 完成了 ADR-0075 的最后实施阶段：

**Task 5: Control Contributions 接入**
- `lca/plugins/control_contributions/` 包含 10 个真实控制插件（11 → 10）
- 每个插件实现 `prepare`、`govern`、`transform`、`observe`、`finalize` 五角色之一
- `tests/declarative/test_control_contributions.py` 验证所有贡献通过 `plugin check --strict`

**Task 6: Legacy Runtime 完全移除**
- 删除 `CognitiveRuntime._loop()`、`_checkpoint()`、`_finish_control_stop()` 和相关 control policy 方法
- 删除 `lca/harness/command/dual_write.py` 及其测试
- `plan_binding.py` 移除 v1 composer fallback，只接受 declarative plans
- 删除 `tests/layer2_runtime/test_checkpoint_atomic.py` 和 `test_control_runtime_execution.py`
- 新增 `tests/architecture/test_declarative_production_closure.py` 守护测试

**Task 7: Effect Idempotency 和 Recovery Profile**
- Step 1: 实现 `RuntimeIdempotencyStore` 于 `lca/layer2_runtime/declarative_runtime.py`
  - `ClaimResult` dataclass 包含 status: `new` / `completed` / `in_progress`
  - `RuntimeEffectGateway` 在执行 effect 前调用 `store.claim()`
  - `completed` 返回已有 receipt；`in_progress` 抛 RT-003 错误
  - 6 个 E2E 测试验证幂等性和 crash 恢复
- Step 2: 创建 recovery profile 配置文件（设计文档）
  - `profiles/web-standard-recovery.yaml` 扩展 web-standard
  - `bundles/declarative-recovery.yaml` 声明 `reflect.main → think.main` recovery edge
  - 注意：完整 recovery plugin 实现延迟到未来工作

**Task 8: ADR 文档更新和架构门禁**
- Step 1: 新增 `test_production_sources_do_not_reference_removed_runtime_modules()`
  - 验证生产代码不导入已删除的 legacy modules
  - 检查 `lca.layer2_runtime.control_policies` 和 `lca.harness.command.dual_write`
- Step 3: 更新 ADR-0075 状态为 Accepted
- 运行 `uv run pytest` 验证所有测试通过

## 最终验收矩阵

| 验证项 | 状态 | 证据 |
|--------|------|------|
| 单一 v2 运行计划 | ✅ | `CompiledRunPlan` 携带 PluginSpec、bindings、图、替换、effect policy |
| 默认 Profile 显式六阶段 | ✅ | `bundles/declarative-phase-graph.yaml` + 6 个 PhaseExecutor |
| 通用编译与解释 | ✅ | `PlanCompiler` + `GraphAssembler` + `GenericPlanInterpreter` |
| 默认 Agent 装配接线 | ✅ | `DeclarativeRuntimeDriver` 为默认路径 |
| 严格工具链 | ✅ | `plugin check --strict`、`plan compile`、`plan validate`、`audit` |
| Effect Gateway 唯一入口 | ✅ | `RuntimeEffectGateway` 为唯一 body/memory 调用点 |
| Journal 事实边界 | ✅ | `RuntimeJournalCommitter` 通过 observability facade |
| 控制贡献执行 | ✅ | `GraphAssembler` 解析 contributions；解释器执行 govern |
| Legacy Runtime 完全移除 | ✅ | `_loop`、`_checkpoint`、`control_policies` 已从生产代码删除 |
| V1 Composer Fallback 移除 | ✅ | `plan_binding.py` 只接受 declarative plans |
| Dual Write 移除 | ✅ | `lca/harness/command/dual_write.py` 及其测试已删除 |
| Effect Idempotency | ✅ | `RuntimeIdempotencyStore` + `RuntimeEffectGateway` claim/complete |
| Recovery Profile 配置 | ⚠️ | YAML 配置文件已创建；完整 plugin 实现延迟 |
| 生产代码无 legacy 引用 | ✅ | `test_production_sources_do_not_reference_removed_runtime_modules()` |

**结论**：ADR-0075 的核心目标已达成。默认生产路径完全由 `CompiledRunPlan` → `GraphAssembler` → `GenericPlanInterpreter` → `RuntimeEffectGateway` 驱动，legacy runtime 和 composer fallback 已完全移除，effect idempotency 已实现。Recovery profile 的完整 plugin 实现作为未来工作延迟。
