# ADR-0075 声明式 PhaseGraph 与最小可信内核：实施审计

> **审计日期：** 2026-08-22
> **审计结论：** 生产认知运行的 ADR-0074/0075 **声明式切换已完成**；ADR-0075 的更广义长期恢复路线尚未全部完成，因此正式 ADR 状态不得提前改为 Accepted。

本审计区分两个范围。第一，**生产切换范围**要求 `CompiledRunPlan`、`PhaseGraph`、插件绑定、通用解释器和 Journal-backed outcome 成为唯一可达运行路径，旧 `_loop`、v1 composer 回退与运行时内具体 control/effect 分派必须移除。该范围已实现。第二，**长期韧性增强范围**包括持久幂等 receipt ledger、计划版本安全边界迁移、受限恢复 Profile 和多 contribution 的完整 `ordered-rewrite` 聚合；这些项目仍须作为后续 ADR-0075 工作完成。

## 已确认的生产切换实现

| ADR-0075 要求 | 当前实现 | 可验证证据 |
|---|---|---|
| 唯一运行计划 | `CompiledRunPlan` 持有声明式图、binding、effect policy 与 validation report；非声明式计划在绑定阶段 fail-closed。 | `lca/contracts/protocols/plan.py`、`lca/plugins/composer/plan_binding.py` |
| 唯一运行编排 | `CognitiveRuntime` 仅创建初始 `AgentState`，并将 `run`/`resume` 委托给 `DeclarativeRuntimeDriver`；旧 `_loop`、`evaluate_control` 与 `DefaultControlPolicyEngine` 已删除。 | `lca/layer2_runtime/runtime_loop.py`、`tests/declarative/test_cutover_characterization.py` |
| 显式六阶段拓扑 | 默认 Profile 编译为 `perceive → think → act → reflect → remember → stop` 的 `PhaseGraph`，CI 脚本验证相邻因果边。 | `bundles/declarative-phase-graph.yaml`、`tools/ci/check_cognitive_loop_order.py` |
| Journal-backed 可恢复结果 | `PhaseRunCursor`、`DeclarativeCheckpoint` 和 `DeclarativeRunOutcome` 是 contracts 数据契约；pause、failed 与 effect_uncertain 均由解释器写入 `RunFact` 后收敛。 | `lca/contracts/protocols/declarative_phase_graph.py`、`lca/harness/declarative/interpreter.py` |
| 审批恢复不重放旧循环 | effect handler 抛出的 `ApprovalPendingError` 被映射为 `run.paused`、cursor 与 `DeclarativeCheckpoint`；网关保存 `declarative_checkpoint`，恢复时由标准 act PhaseExecutor 产出通用 human-input receipt，而非重放暂停 effect。 | `gateway/runs/execute.py`、`gateway/runs/session.py`、`lca/plugins/phase_executors/common.py`、`tests/test_run_hil.py` |
| 控制为声明式贡献 | 默认 `control.standard` 在各 phase 以 GOVERN contribution 产生 allow/deny/stop/pause verdict；解释器在 effect 前执行贡献并对 deny fail-closed。 | `lca/plugins/control_contributions/standard.py`、`tests/declarative/test_standard_control_contribution.py` |
| 效果为 capability-bound handler | PhaseExecutor 只 mint `CommandEnvelope`；通用 Gateway 按 grant capability 路由至可替换的 `body.act` / `memory.update` handler，不按 operation、插件 ID 或工具名进行业务分派。 | `lca/layer2_runtime/declarative_runtime.py`、`lca/plugins/effect_handlers/`、`tests/declarative/test_effect_handler_binding.py` |
| 旧 control 双轨删除 | `control_policies.py`、其旧运行测试与旧 runtime 调用点均已删除。 | `tests/declarative/test_cutover_characterization.py` |

> 生产 Runtime、Composer 与 EffectGateway 不再拥有按工具名、默认插件名或业务操作分派的旧循环路径。能力选择由 Profile → `PluginSpec` → binding → `PhaseGraph` 表达。

## 已验证的行为边界

| 行为 | 验证结果 |
|---|---|
| 默认图顺序 | `tools/ci/check_cognitive_loop_order.py` 成功输出六阶段声明式拓扑。 |
| 控制暂停与继续 | Govern pause 返回带 cursor 的 `paused` outcome，并从同一编译计划继续。 |
| effect 审批等待 | `ApprovalPendingError` 转为 Journal-backed `run.paused`；HIL HTTP 流程保持 tail 打开并在回答后完成。 |
| effect 不确定 | 未确认 receipt 返回 `effect_uncertain`，而非自动重放 effect。 |
| 控制拒绝 | deny/stop 在 effect 前截断，并返回真实 `failed` outcome；driver 不再写入 `outcome=completed`。 |
| 旧路径闭包 | source-level characterization 断言 `_loop`、旧 control module 与 v1 composer fallback 不可达。 |

## 未完成范围与后续门槛

| 项目 | 当前状态 | 不能提前宣称的能力 |
|---|---|---|
| 持久幂等 claim / receipt ledger | 未实现。当前 cursor 防止已确认 effect 在同一恢复路径中重放，但没有跨进程持久 receipt claim 协议。 | 严格的崩溃后 exactly-once / 可证明 at-most-once 世界效果。 |
| plan revision 安全边界 | 未实现。checkpoint 会校验 `plan_ref` 并 fail-closed。 | 在计划升级时自动迁移或继续长程运行。 |
| bounded recovery Profile | 未实现。当前使用通用暂停/失败结果，未定义专用恢复策略图。 | 针对错误类别的受限自动重试、降级与转交策略。 |
| `ordered-rewrite` 多贡献聚合 | 仅覆盖默认 allow/deny/pause/stop 与第一个终端 verdict。 | 任意多个 rewrite contribution 的完整有序组合语义。 |
| 全仓静态基线 | 存在既有 `lint-imports`、`mypy lca`、`vulture` 与第三方 `vendor/cordis` Ruff 违规。此次切换没有新增 checkpoint 的反向分层依赖；最终提交报告必须如实单列这些基线问题。 | “所有仓库静态质量门禁全绿”的声明。 |

因此，ADR-0075 当前应维持为**实施中的决定**：生产切换代码已落地，但仍需完成上述持久恢复项目后，才能把长期 Agent 的恢复、自愈与幂等保证描述为完整实现。

## 关联资料

- 正式 ADR：`docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md`
- 切换计划：`docs/superpowers/plans/2026-08-22-adr-74-75-declarative-cutover.md`
- 图契约规范：`docs/specs/declarative-phase-graph-spec.md`
- ADR-0074 验收与 tracker：`docs/plans/adr-0074-acceptance-criteria.md`、`docs/plans/adr-0074-plugin-everything-tracker.md`
