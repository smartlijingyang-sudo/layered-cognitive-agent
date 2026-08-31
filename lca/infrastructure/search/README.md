# lca/infrastructure/search

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `8` 个公开模块 + `25` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：13 个显式 __all__ 条目； 25 个定义符号中，23 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.infrastructure.search].forbidden_dependencies`**:

- `gateway`
- `lca.agent`
- `lca.application`
- `lca.cognition`
- `lca.harness`
- `lca.plugins`
- `lca.runtime`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `LOBE_WEB_BROWSING_ID`
- `PROVIDER_LLM_NATIVE`
- `PROVIDER_TAVILY`
- `WEB_BROWSING_API_SEARCH`
- `WEB_SEARCH_TOOL`
- `any_search_provider_available`
- `get_search_settings`
- `is_search_intent`
- `resolve_llm_search_kwargs`
- `search`
- `search_routing_hint`
- `search_run_scope`
- `web_search`

**模块清单**:

- `lca/infrastructure/search/constants.py`
- `lca/infrastructure/search/models.py`
- `lca/infrastructure/search/router.py`
- `lca/infrastructure/search/scope.py`
- `lca/infrastructure/search/service.py`
- `lca/infrastructure/search/settings.py`
- `lca/infrastructure/search/skill_policy.py`
- `lca/infrastructure/search/tavily.py`
