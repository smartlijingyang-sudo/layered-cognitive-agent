# lca/cognition

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `68` 个公开模块 + `354` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 354 个定义符号中，231 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.cognition].forbidden_dependencies`**:

- `gateway`
- `lca.agent`
- `lca.application`
- `lca.harness`
- `lca.plugins`
- `lca.runtime`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `lca/cognition/_loader.py`
- `lca/cognition/action_catalog.py`
- `lca/cognition/action_handlers.py`
- `lca/cognition/action_registry.py`
- `lca/cognition/artifact_respond_injector.py`
- `lca/cognition/blackboard.py`
- `lca/cognition/chained.py`
- `lca/cognition/clock.py`
- `lca/cognition/cognitive_pipeline.py`
- `lca/cognition/consult_policy.py`
- `lca/cognition/context_manifest.py`
- `lca/cognition/conversation_prompt.py`
- `lca/cognition/critic.py`
- `lca/cognition/default_factory.py`
- `lca/cognition/delegation_cache.py`
- `lca/cognition/delegation_target.py`
- `lca/cognition/event_bus.py`
- `lca/cognition/executor.py`
- `lca/cognition/gate_service.py`
- `lca/cognition/group_assembly.py`
- `lca/cognition/hook_registry.py`
- `lca/cognition/in_memory.py`
- `lca/cognition/journal_backed.py`
- `lca/cognition/layered_retrieval_policy.py`
- `lca/cognition/leaked_tool_call.py`
- `lca/cognition/mode.py`
- `lca/cognition/modular_brain.py`
- `lca/cognition/must_consult_all.py`
- `lca/cognition/null_critic.py`
- `lca/cognition/null_retrieval_policy.py`
- ... 共 68 个
