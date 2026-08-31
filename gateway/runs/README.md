# gateway/runs

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `56` 个公开模块 + `261` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 261 个定义符号中，208 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.gateway.runs].forbidden_dependencies`**:

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
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `gateway/runs/artifact_closure.py`
- `gateway/runs/attachment_staging.py`
- `gateway/runs/binding.py`
- `gateway/runs/builder.py`
- `gateway/runs/cache.py`
- `gateway/runs/command_endpoints.py`
- `gateway/runs/diagnostics.py`
- `gateway/runs/doctor.py`
- `gateway/runs/environment_bindings.py`
- `gateway/runs/error_presentation.py`
- `gateway/runs/evidence.py`
- `gateway/runs/execute.py`
- `gateway/runs/execute.py`
- `gateway/runs/execution_environment.py`
- `gateway/runs/export_disposal.py`
- `gateway/runs/failure.py`
- `gateway/runs/fetcher.py`
- `gateway/runs/file_reference_parsing.py`
- `gateway/runs/health.py`
- `gateway/runs/identity.py`
- `gateway/runs/index.py`
- `gateway/runs/ingest.py`
- `gateway/runs/ingress.py`
- `gateway/runs/integrity.py`
- `gateway/runs/intent.py`
- `gateway/runs/journal.py`
- `gateway/runs/journal_projection_binding.py`
- `gateway/runs/legacy.py`
- `gateway/runs/legacy_adapter.py`
- `gateway/runs/lifecycle.py`
- ... 共 56 个
