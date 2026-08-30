# lca/plugins

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `245` 个公开模块 + `401` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 401 个定义符号中，315 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
—

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `lca/plugins/_chunk.py`
- `lca/plugins/_encoder.py`
- `lca/plugins/_encoder.py`
- `lca/plugins/_helpers.py`
- `lca/plugins/_standard_factory.py`
- `lca/plugins/act.py`
- `lca/plugins/act_authorize.py`
- `lca/plugins/act_budget.py`
- `lca/plugins/act_constrain.py`
- `lca/plugins/act_execute.py`
- `lca/plugins/act_safe_boundary.py`
- `lca/plugins/action_authority.py`
- `lca/plugins/action_handler.py`
- `lca/plugins/action_handlers.py`
- `lca/plugins/agent.py`
- `lca/plugins/agent_assembly.py`
- `lca/plugins/aggregator.py`
- `lca/plugins/artifact_closure.py`
- `lca/plugins/artifact_closure.py`
- `lca/plugins/artifact_respond_injector.py`
- `lca/plugins/attachment.py`
- `lca/plugins/attachment.py`
- `lca/plugins/attribute_policy.py`
- `lca/plugins/attribute_policy.py`
- `lca/plugins/auto_acquire.py`
- `lca/plugins/bash.py`
- `lca/plugins/blackboard.py`
- `lca/plugins/body_composer.py`
- `lca/plugins/body_provider.py`
- `lca/plugins/brain.py`
- ... 共 245 个
