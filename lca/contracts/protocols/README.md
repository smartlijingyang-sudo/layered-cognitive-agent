# lca/contracts/protocols

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `52` 个公开模块 + `401` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：194 个显式 __all__ 条目； 401 个定义符号中，395 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
—

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `ActionAuthorityPlan`
- `ActionHandler`
- `ActionHandlerRegistry`
- `ActionScopeAuthority`
- `AgentTransport`
- `AgentUnit`
- `ApprovalResumeDecision`
- `ApprovalResumeDisposition`
- `ArtifactClosure`
- `AttachmentIdentity`
- `Body`
- `Brain`
- `BrainFactory`
- `BrainPromptCatalog`
- `BrainPromptCatalogFactory`
- `BudgetAware`
- `BudgetCeiling`
- `BudgetPolicy`
- `BudgetReservation`
- `COMPILED_RUN_PLAN_VERSION`
- `CapabilityBinding`
- `CapabilityDeclaration`
- `CapabilityGrant`
- `CapabilityPlan`
- `CheckpointStateResolver`
- `CheckpointStateResolverFactory`
- `CognitivePhaseGraphPlan`
- `CognitiveReflectionPipeline`
- `CognitiveThinkPipeline`
- `CommandEnvelope`
- ... 共 194 项

**模块清单**:

- `lca/contracts/protocols/action.py`
- `lca/contracts/protocols/action_handler.py`
- `lca/contracts/protocols/agent.py`
- `lca/contracts/protocols/artifact_closure.py`
- `lca/contracts/protocols/capabilities.py`
- `lca/contracts/protocols/capability_plan.py`
- `lca/contracts/protocols/casting.py`
- `lca/contracts/protocols/cognition.py`
- `lca/contracts/protocols/cognitive_pipeline.py`
- `lca/contracts/protocols/command_envelope.py`
- `lca/contracts/protocols/control_verdict.py`
- `lca/contracts/protocols/decision_classifier.py`
- `lca/contracts/protocols/declarative_capability.py`
- `lca/contracts/protocols/declarative_common.py`
- `lca/contracts/protocols/declarative_execution.py`
- `lca/contracts/protocols/declarative_fault_tolerance.py`
- `lca/contracts/protocols/declarative_graph.py`
- `lca/contracts/protocols/declarative_phase_graph.py`
- `lca/contracts/protocols/declarative_plugin.py`
- `lca/contracts/protocols/delta_handler.py`
- `lca/contracts/protocols/effect_handler.py`
- `lca/contracts/protocols/embodiment.py`
- `lca/contracts/protocols/gate_chain_composer.py`
- `lca/contracts/protocols/graph_node_executor.py`
- `lca/contracts/protocols/idempotency.py`
- `lca/contracts/protocols/infra.py`
- `lca/contracts/protocols/journal.py`
- `lca/contracts/protocols/lead_budget_policy.py`
- `lca/contracts/protocols/learning.py`
- `lca/contracts/protocols/logic_address.py`
- ... 共 52 个
