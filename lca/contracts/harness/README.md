# lca.contracts.harness

> 状态：稳定 | 草稿 | 弃用
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
lca/contracts/harness. 职责见各包 docstring 与 .py 文件注释；本 README 由脚手架生成，等待包负责人补充具体职责描述

## 2. 不负责
实现细节、I/O、配置解析、业务编排

## 3. 输入
{{inputs}}

## 4. 输出
{{outputs}}

## 5. 允许依赖
lca.contracts

## 6. 禁止依赖
lca.infrastructure,lca.cognition,lca.runtime,lca.agent,lca.application,lca.harness,lca.plugins

## 7. 副作用


## 8. 失败语义
{{failure_semantics}}

## 9. 公共入口
`AgentGraph`, `AgentGraphComposer`, `AgentGraphContribution`, `ArchitectureContract`, `ArtifactController`, `AuthorityContract`, `CapabilityArtifact`, `CapabilityContract`, `ContinuousControlPlane`, `ContinuousControlPlaneFactory`, `EvidenceContract`, `InvalidStateTransitionError`, `LifecycleContract`, `OwnershipContract`, `PluginContract`, `PluginIdentity`, `SessionWorkActivator`, `TeamGraph`, `TeamGraphComposer`, `Trigger`, `TriggerKind`, `VerificationContract`, `WorkActivationReceipt`, `WorkItem`, `WorkLease`, `WorkQueue`, `WorkStatus`, `artifact_with_state`, `capability_artifact_to_dict`, `is_plugin_contract_empty`, `is_terminal_state`, `legal_next_states`, `make_capability_artifact`, `merge_agent_graphs`, `migrate_artifact`, `migrate_to_active`, `migrate_to_retired`, `migrate_to_verified`, `plugin_contract_control_slots`, `plugin_contract_functional_group`

