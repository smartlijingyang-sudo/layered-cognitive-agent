# lca/plugins/gates

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `8` 个公开模块 + `4` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 4 个定义符号中，4 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.plugins.gates].forbidden_dependencies`**:

- `gateway`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `lca/plugins/gates/artifact_respond_injector.py`
- `lca/plugins/gates/chained.py`
- `lca/plugins/gates/must_consult_all.py`
- `lca/plugins/gates/progress_loop_detector.py`
- `lca/plugins/gates/repeat_tool_call.py`
- `lca/plugins/gates/service.py`
- `lca/plugins/gates/terminal_respond.py`
- `lca/plugins/gates/tool_loop_breaker.py`
