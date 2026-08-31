# lca/contracts/harness

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `36` 个公开模块 + `231` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：40 个显式 __all__ 条目； 231 个定义符号中，228 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.contracts.harness].forbidden_dependencies`**:

- `lca.agent`
- `lca.application`
- `lca.cognition`
- `lca.harness`
- `lca.infrastructure`
- `lca.plugins`
- `lca.runtime`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `AgentGraph`
- `AgentGraphComposer`
- `AgentGraphContribution`
- `ArchitectureContract`
- `ArtifactController`
- `AuthorityContract`
- `CapabilityArtifact`
- `CapabilityContract`
- `ContinuousControlPlane`
- `ContinuousControlPlaneFactory`
- `EvidenceContract`
- `InvalidStateTransitionError`
- `LifecycleContract`
- `OwnershipContract`
- `PluginContract`
- `PluginIdentity`
- `SessionWorkActivator`
- `TeamGraph`
- `TeamGraphComposer`
- `Trigger`
- `TriggerKind`
- `VerificationContract`
- `WorkActivationReceipt`
- `WorkItem`
- `WorkLease`
- `WorkQueue`
- `WorkStatus`
- `artifact_with_state`
- `capability_artifact_to_dict`
- `is_plugin_contract_empty`
- `is_terminal_state`
- `legal_next_states`
- `make_capability_artifact`
- `merge_agent_graphs`
- `migrate_artifact`
- `migrate_to_active`
- `migrate_to_retired`
- `migrate_to_verified`
- `plugin_contract_control_slots`
- `plugin_contract_functional_group`
