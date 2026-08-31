# lca/plugins/providers

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `60` 个公开模块 + `124` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 124 个定义符号中，91 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.plugins.providers].forbidden_dependencies`**:

- `gateway`

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
（无显式 __all__；通过模块导入即可）

**模块清单**:

- `lca/plugins/providers/_chunk.py`
- `lca/plugins/providers/_encoder.py`
- `lca/plugins/providers/_encoder.py`
- `lca/plugins/providers/action_handlers.py`
- `lca/plugins/providers/artifact_closure.py`
- `lca/plugins/providers/attachment.py`
- `lca/plugins/providers/attribute_policy.py`
- `lca/plugins/providers/cli_debug_trace.py`
- `lca/plugins/providers/cognitive_reflection_pipeline.py`
- `lca/plugins/providers/cognitive_think_pipeline.py`
- `lca/plugins/providers/component_budget_policy.py`
- `lca/plugins/providers/component_memory.py`
- `lca/plugins/providers/component_state_store.py`
- `lca/plugins/providers/composition_composer.py`
- `lca/plugins/providers/composition_provider.py`
- `lca/plugins/providers/continuous_control_plane.py`
- `lca/plugins/providers/decision_classifier.py`
- `lca/plugins/providers/declarative_runtime_seams.py`
- `lca/plugins/providers/delta_handler_registry.py`
- `lca/plugins/providers/delta_handlers.py`
- `lca/plugins/providers/effect_handlers.py`
- `lca/plugins/providers/event_descriptor.py`
- `lca/plugins/providers/evidence_store_filesystem.py`
- `lca/plugins/providers/fact_reader_console.py`
- `lca/plugins/providers/fact_reader_jsonl.py`
- `lca/plugins/providers/fact_reader_langfuse.py`
- `lca/plugins/providers/fact_reader_otel.py`
- `lca/plugins/providers/fact_scorer_langfuse.py`
- `lca/plugins/providers/fact_store_memory.py`
- `lca/plugins/providers/file_store.py`
- ... 共 60 个
