# lca/harness/declarative

> 状态：稳定（v2-only；GraphAssembler 已退役）
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
声明式最小可信内核的编译辅助、控制面与生命周期观测。Profile + Bundle
经 kernel plan compile 得到不可变 `CompiledRunPlan`；**生产执行**由
`lca.framework.graph.interpreter.PlanInterpreter` 直接驱动 v2
`BundleGraphSpec`（ADR-0217 / ADR-0218 / ADR-0220 / ADR-0221 P3）。

v0 `GraphAssembler` / `ExecutablePlan` / `MappingRestrictedScope` 已删除
（delete-when ≤ `eng/retire-v1-reasoner-sandbox`）。从本包 import 这些
符号会 `AttributeError` fail-loud。

## 2. 不负责
运行时效果实现、I/O、网络——这些由 plugins/seams/* 与 infrastructure/ 提供。
图遍历与节点调度——由 `lca.framework.graph` 负责。

## 3. 输入
- compile（subgraph_resolver / subgraph_validation / instrument / authority / effect）
- controls（approval / validation）
- lifecycle（phase_context / phase_observation）
- execute（dispatch）

## 4. 输出
**__init__.py 显式 __all__**:

- `ApprovalState`
- `ApprovalStateMachine`
- `ApprovalTransition`
- `RestrictedPhaseContext`
- `validate_control_binding_closure`

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
模块导入失败 → ImportError；退役符号 → AttributeError（fail-loud）；
运行时错误以 L1 protocol 中定义的异常类型抛出。
