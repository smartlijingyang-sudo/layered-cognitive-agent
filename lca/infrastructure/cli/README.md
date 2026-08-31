# lca/infrastructure/cli

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `27` 个公开模块 + `235` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 235 个定义符号中，175 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.infrastructure.cli].forbidden_dependencies`**:

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
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `lca/infrastructure/cli/_shared.py`
- `lca/infrastructure/cli/audit.py`
- `lca/infrastructure/cli/cli.py`
- `lca/infrastructure/cli/config.py`
- `lca/infrastructure/cli/console.py`
- `lca/infrastructure/cli/creator_plan.py`
- `lca/infrastructure/cli/daemon.py`
- `lca/infrastructure/cli/declarative.py`
- `lca/infrastructure/cli/declarative_graph.py`
- `lca/infrastructure/cli/diagnostics.py`
- `lca/infrastructure/cli/gateway.py`
- `lca/infrastructure/cli/infra.py`
- `lca/infrastructure/cli/journal.py`
- `lca/infrastructure/cli/journal_log.py`
- `lca/infrastructure/cli/lobehub.py`
- `lca/infrastructure/cli/onlyboxes.py`
- `lca/infrastructure/cli/package_organization.py`
- `lca/infrastructure/cli/pipeline.py`
- `lca/infrastructure/cli/profile_inspect.py`
- `lca/infrastructure/cli/registry.py`
- `lca/infrastructure/cli/service.py`
- `lca/infrastructure/cli/services.py`
- `lca/infrastructure/cli/state.py`
- `lca/infrastructure/cli/steps.py`
- `lca/infrastructure/cli/sudo.py`
- `lca/infrastructure/cli/tools.py`
- `lca/infrastructure/cli/workflow.py`
