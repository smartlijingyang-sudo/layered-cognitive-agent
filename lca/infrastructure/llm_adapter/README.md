# lca/infrastructure/llm_adapter

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `13` 个公开模块 + `85` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：12 个显式 __all__ 条目； 85 个定义符号中，45 个为公共命名

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

- `FailoverLLMAdapter`
- `LLMApiStyle`
- `LLMFailoverCandidate`
- `LLMRetryPolicy`
- `LLMSettings`
- `MockLLMAdapter`
- `OpenAICompatAdapter`
- `RetryingLLMAdapter`
- `clear_llm_settings_cache`
- `get_llm_settings`
- `load_dotenv_if_present`
- `resolve_llm_adapter`

**模块清单**:

- `lca/infrastructure/llm_adapter/_anthropic_messages.py`
- `lca/infrastructure/llm_adapter/_anthropic_stream.py`
- `lca/infrastructure/llm_adapter/_chat_completions.py`
- `lca/infrastructure/llm_adapter/_history.py`
- `lca/infrastructure/llm_adapter/_responses.py`
- `lca/infrastructure/llm_adapter/_shared.py`
- `lca/infrastructure/llm_adapter/_strategy.py`
- `lca/infrastructure/llm_adapter/api_style.py`
- `lca/infrastructure/llm_adapter/factory.py`
- `lca/infrastructure/llm_adapter/failover.py`
- `lca/infrastructure/llm_adapter/mock_llm.py`
- `lca/infrastructure/llm_adapter/settings.py`
- `lca/infrastructure/llm_adapter/tool_arguments.py`
