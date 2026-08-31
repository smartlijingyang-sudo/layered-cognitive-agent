# lca/contracts/observability

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `21` 个公开模块 + `130` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：8 个显式 __all__ 条目； 130 个定义符号中，126 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.contracts.observability].forbidden_dependencies`**:

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
**__init__.py 显式 __all__**:

- `Classification`
- `EvidenceIntegrityError`
- `EvidencePolicy`
- `EvidenceReceipt`
- `EvidenceRef`
- `EvidenceStore`
- `RetentionClass`
- `RunLedgerFactory`

**模块清单**:

- `lca/contracts/observability/cli_debug_command.py`
- `lca/contracts/observability/coding_agent_tools.py`
- `lca/contracts/observability/cost.py`
- `lca/contracts/observability/error_codes.py`
- `lca/contracts/observability/event_descriptor_registry.py`
- `lca/contracts/observability/event_identity.py`
- `lca/contracts/observability/evidence.py`
- `lca/contracts/observability/genai_semantic.py`
- `lca/contracts/observability/journal_formatter.py`
- `lca/contracts/observability/journal_store.py`
- `lca/contracts/observability/ledger.py`
- `lca/contracts/observability/migrate.py`
- `lca/contracts/observability/named_registry.py`
- `lca/contracts/observability/ports.py`
- `lca/contracts/observability/run_journal.py`
- `lca/contracts/observability/run_locator.py`
- `lca/contracts/observability/run_manifest.py`
- `lca/contracts/observability/session_events.py`
- `lca/contracts/observability/trace_tool.py`
- `lca/contracts/observability/v2.py`
- `lca/contracts/observability/w3c_trace_context.py`
