# lca/infrastructure/sandbox

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `18` 个公开模块 + `84` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：2 个显式 __all__ 条目； 84 个定义符号中，67 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.infrastructure.sandbox].forbidden_dependencies`**:

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

- `OnlyboxesSandboxAdapter`
- `resolve_sandbox`

**模块清单**:

- `lca/infrastructure/sandbox/artifact_scanner.py`
- `lca/infrastructure/sandbox/bootstrap.py`
- `lca/infrastructure/sandbox/error_parse.py`
- `lca/infrastructure/sandbox/exec_result.py`
- `lca/infrastructure/sandbox/factory.py`
- `lca/infrastructure/sandbox/host_settings.py`
- `lca/infrastructure/sandbox/inspect_prelude.py`
- `lca/infrastructure/sandbox/onlyboxes_adapter.py`
- `lca/infrastructure/sandbox/onlyboxes_artifacts.py`
- `lca/infrastructure/sandbox/onlyboxes_bootstrap.py`
- `lca/infrastructure/sandbox/output_collect.py`
- `lca/infrastructure/sandbox/paths.py`
- `lca/infrastructure/sandbox/prompt.py`
- `lca/infrastructure/sandbox/runtime.py`
- `lca/infrastructure/sandbox/runtime_mount.py`
- `lca/infrastructure/sandbox/runtime_scope.py`
- `lca/infrastructure/sandbox/streaming.py`
- `lca/infrastructure/sandbox/surface.py`
