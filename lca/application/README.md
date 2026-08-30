# lca/application

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `12` 个公开模块 + `88` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：5 个显式 __all__ 条目； 88 个定义符号中，66 个为公共命名

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
- `Team`
- `TeamLead`
- `spawn_agent`
- `spawn_team`

**模块清单**:

- `lca/application/api.py`
- `lca/application/casting.py`
- `lca/application/default_context.py`
- `lca/application/followup_dispatch.py`
- `lca/application/harness_bridge.py`
- `lca/application/harness_live.py`
- `lca/application/live_session_state.py`
- `lca/application/policies.py`
- `lca/application/preset_authoring.py`
- `lca/application/role_suggest.py`
- `lca/application/session_live_builder_provider.py`
- `lca/application/spawn.py`
