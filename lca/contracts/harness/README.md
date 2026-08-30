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
—

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
- ... 共 40 项

**模块清单**:

- `lca/contracts/harness/agent.py`
- `lca/contracts/harness/artifact.py`
- `lca/contracts/harness/artifact_manifest.py`
- `lca/contracts/harness/cancellation.py`
- `lca/contracts/harness/capability_gate.py`
- `lca/contracts/harness/command.py`
- `lca/contracts/harness/compensation.py`
- `lca/contracts/harness/composer.py`
- `lca/contracts/harness/context_budget.py`
- `lca/contracts/harness/continuous.py`
- `lca/contracts/harness/cost_snapshot.py`
- `lca/contracts/harness/delegation_grant.py`
- `lca/contracts/harness/effect_receipt.py`
- `lca/contracts/harness/eval_case.py`
- `lca/contracts/harness/eval_comparison.py`
- `lca/contracts/harness/events.py`
- `lca/contracts/harness/evidence.py`
- `lca/contracts/harness/handoff.py`
- `lca/contracts/harness/middleware.py`
- `lca/contracts/harness/plugin.py`
- `lca/contracts/harness/plugin_contract.py`
- `lca/contracts/harness/plugin_meta.py`
- `lca/contracts/harness/projection.py`
- `lca/contracts/harness/replan.py`
- `lca/contracts/harness/result_verifier.py`
- `lca/contracts/harness/sandbox_limits.py`
- `lca/contracts/harness/session.py`
- `lca/contracts/harness/skill.py`
- `lca/contracts/harness/sse_cursor.py`
- `lca/contracts/harness/subagent.py`
- ... 共 36 个
