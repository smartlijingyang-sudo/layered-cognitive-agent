# lca/infrastructure

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `277` 个公开模块 + `1531` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 1531 个定义符号中，1043 个为公共命名

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

- `lca/infrastructure/_anthropic_messages.py`
- `lca/infrastructure/_anthropic_stream.py`
- `lca/infrastructure/_chat_completions.py`
- `lca/infrastructure/_format.py`
- `lca/infrastructure/_history.py`
- `lca/infrastructure/_responses.py`
- `lca/infrastructure/_shared.py`
- `lca/infrastructure/_shared.py`
- `lca/infrastructure/_strategy.py`
- `lca/infrastructure/a2a_transport.py`
- `lca/infrastructure/activate_tool.py`
- `lca/infrastructure/activation_scope.py`
- `lca/infrastructure/adapters.py`
- `lca/infrastructure/agent_transport.py`
- `lca/infrastructure/api_style.py`
- `lca/infrastructure/archive.py`
- `lca/infrastructure/artifact_ledger.py`
- `lca/infrastructure/artifact_scanner.py`
- `lca/infrastructure/audit.py`
- `lca/infrastructure/background.py`
- `lca/infrastructure/bootstrap.py`
- `lca/infrastructure/builder.py`
- `lca/infrastructure/builtin.py`
- `lca/infrastructure/bundled.py`
- `lca/infrastructure/catalog.py`
- `lca/infrastructure/cli.py`
- `lca/infrastructure/cli_json.py`
- `lca/infrastructure/client.py`
- `lca/infrastructure/codegen_ts.py`
- `lca/infrastructure/cognitive_loop_settings.py`
- ... 共 277 个
