# lca/harness/declarative

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
声明式最小可信内核的编译、装配与执行实现。PlanCompiler 把 Profile + PluginSpec 转成不可变 CompiledRunPlan；GraphAssembler 把 plan 闭包为 AgentGraph；PhaseGraphInterpreter 执行遍历；5 个子包（compile、graph、execute、lifecycle、controls）按 phase-graph 责任分工。

## 2. 不负责
运行时效果实现、I/O、网络——这些由 plugins/seams/* 与 infrastructure/ 提供。

## 3. 输入
- 当前包内 `24` 个公开模块 + `175` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：16 个显式 __all__ 条目； 175 个定义符号中，103 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.harness.declarative].forbidden_dependencies`**:

- `lca.agent`
- `lca.application`
- `lca.cognition`
- `lca.runtime`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `ApprovalState`
- `ApprovalStateMachine`
- `ApprovalTransition`
- `DeclarativePlanProjection`
- `ExecutableNode`
- `ExecutablePlan`
- `GenericPlanInterpreter`
- `GraphAssembler`
- `InMemoryJournalCommitter`
- `InterpretationResult`
- `MappingRestrictedScope`
- `PhaseVisit`
- `RestrictedPhaseContext`
- `RestrictedScope`
- `compile_declarative_projection`
- `validate_control_binding_closure`

**模块清单**:

- `lca/harness/declarative/action_authority.py`
- `lca/harness/declarative/approval.py`
- `lca/harness/declarative/assembler.py`
- `lca/harness/declarative/authority.py`
- `lca/harness/declarative/compiler.py`
- `lca/harness/declarative/dispatch.py`
- `lca/harness/declarative/effect_policy.py`
- `lca/harness/declarative/effect_receipt.py`
- `lca/harness/declarative/graph_algorithms.py`
- `lca/harness/declarative/graph_validation.py`
- `lca/harness/declarative/interpreter.py`
- `lca/harness/declarative/loop_guard.py`
- `lca/harness/declarative/outcome_projection.py`
- `lca/harness/declarative/phase_capabilities.py`
- `lca/harness/declarative/phase_context.py`
- `lca/harness/declarative/phase_execution_policy.py`
- `lca/harness/declarative/phase_governance.py`
- `lca/harness/declarative/phase_graph_compiler.py`
- `lca/harness/declarative/phase_observation.py`
- `lca/harness/declarative/phase_observation_snapshot.py`
- `lca/harness/declarative/phase_transaction.py`
- `lca/harness/declarative/predicate.py`
- `lca/harness/declarative/traversal.py`
- `lca/harness/declarative/validation.py`
