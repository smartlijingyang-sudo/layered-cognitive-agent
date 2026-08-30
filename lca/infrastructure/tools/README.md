# lca/infrastructure/tools

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `39` 个公开模块 + `106` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：8 个显式 __all__ 条目； 106 个定义符号中，74 个为公共命名

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

- `SANDBOX_EXECUTE_TOOL_NAME`
- `SANDBOX_INSPECT_TOOL_NAME`
- `SandboxExecuteTool`
- `SandboxInspectTool`
- `build_default_tools`
- `get_current_run_attachment_ids`
- `merge_attachment_ids`
- `run_attachment_scope`

**模块清单**:

- `lca/infrastructure/tools/_format.py`
- `lca/infrastructure/tools/activate_tool.py`
- `lca/infrastructure/tools/builder.py`
- `lca/infrastructure/tools/builtin.py`
- `lca/infrastructure/tools/codegen_ts.py`
- `lca/infrastructure/tools/default_set.py`
- `lca/infrastructure/tools/edit_file.py`
- `lca/infrastructure/tools/exec_tool.py`
- `lca/infrastructure/tools/execute_code.py`
- `lca/infrastructure/tools/executor.py`
- `lca/infrastructure/tools/export_file.py`
- `lca/infrastructure/tools/get_command_output.py`
- `lca/infrastructure/tools/glob_files.py`
- `lca/infrastructure/tools/grep_content.py`
- `lca/infrastructure/tools/import_tool.py`
- `lca/infrastructure/tools/kill_command.py`
- `lca/infrastructure/tools/list_files.py`
- `lca/infrastructure/tools/manifest.py`
- `lca/infrastructure/tools/manifest.py`
- `lca/infrastructure/tools/move_files.py`
- `lca/infrastructure/tools/observations.py`
- `lca/infrastructure/tools/project.py`
- `lca/infrastructure/tools/read_file.py`
- `lca/infrastructure/tools/read_reference_tool.py`
- `lca/infrastructure/tools/render.py`
- `lca/infrastructure/tools/run_attachment_scope.py`
- `lca/infrastructure/tools/run_command.py`
- `lca/infrastructure/tools/run_finalizer.py`
- `lca/infrastructure/tools/sandbox_contracts.py`
- `lca/infrastructure/tools/sandbox_exec_observation.py`
- ... 共 39 个
