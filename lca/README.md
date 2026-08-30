# lca

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `895` 个公开模块 + `3790` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：14 个显式 __all__ 条目； 3790 个定义符号中，2828 个为公共命名

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

- `Agent`
- `AgentSpec`
- `Debate`
- `FanOut`
- `Governance`
- `Graph`
- `LeadMandate`
- `LeadSpec`
- `PeerRelay`
- `PeerSwarm`
- `Pipeline`
- `Team`
- `TeamLead`
- `TeamSpec`

**模块清单**:

- `lca/_anthropic_messages.py`
- `lca/_anthropic_stream.py`
- `lca/_chat_completions.py`
- `lca/_chunk.py`
- `lca/_encoder.py`
- `lca/_encoder.py`
- `lca/_finalize.py`
- `lca/_format.py`
- `lca/_helpers.py`
- `lca/_history.py`
- `lca/_loader.py`
- `lca/_responses.py`
- `lca/_shared.py`
- `lca/_shared.py`
- `lca/_standard_factory.py`
- `lca/_strategy.py`
- `lca/a2a_transport.py`
- `lca/act.py`
- `lca/act_authorize.py`
- `lca/act_budget.py`
- `lca/act_constrain.py`
- `lca/act_execute.py`
- `lca/act_safe_boundary.py`
- `lca/action.py`
- `lca/action_authority.py`
- `lca/action_authority.py`
- `lca/action_catalog.py`
- `lca/action_handler.py`
- `lca/action_handler.py`
- `lca/action_handlers.py`
- ... 共 895 个
