# lca/runtime

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `16` 个公开模块 + `113` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：4 个显式 __all__ 条目； 113 个定义符号中，87 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.runtime].forbidden_dependencies`**:

- `gateway`
- `lca.agent`
- `lca.application`
- `lca.harness`
- `lca.plugins`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `AgentPhase`
- `CognitiveRuntime`

**模块清单**:

- `lca/runtime/checkpoint_resolution.py`
- `lca/runtime/declarative_runtime.py`
- *(module removed per ADR-0169 §D9)*
- `lca/runtime/idempotency_fixtures.py`
- `lca/runtime/phase_capabilities.py`
- `lca/runtime/phases.py`
- `lca/runtime/reducer.py`
- `lca/runtime/result_finalizer.py`
- `lca/runtime/result_projection.py`
- `lca/runtime/resume_input.py`
- `lca/runtime/runtime_bindings.py`
- `lca/runtime/runtime_event_publisher.py`
- `lca/runtime/runtime_journal.py`
- `lca/runtime/runtime_lifecycle.py`
- `lca/runtime/runtime_lifecycle_emitter.py`
- `lca/runtime/runtime_loop.py`
