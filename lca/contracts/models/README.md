# lca/contracts/models

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `42` 个公开模块 + `259` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 259 个定义符号中，240 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.contracts.models].forbidden_dependencies`**:

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

- `lca/contracts/models/activation.py`
- `lca/contracts/models/approval.py`
- `lca/contracts/models/attachment.py`
- `lca/contracts/models/budget.py`
- `lca/contracts/models/consultation.py`
- `lca/contracts/models/conversation.py`
- `lca/contracts/models/decision.py`
- `lca/contracts/models/delegation.py`
- `lca/contracts/models/delegation_context.py`
- `lca/contracts/models/diagnostic.py`
- `lca/contracts/models/event.py`
- `lca/contracts/models/execution.py`
- `lca/contracts/models/gate_policy.py`
- `lca/contracts/models/graph.py`
- `lca/contracts/models/guest_layout.py`
- `lca/contracts/models/journal.py`
- `lca/contracts/models/journal_catalog.py`
- `lca/contracts/models/lifecycle.py`
- `lca/contracts/models/llm.py`
- `lca/contracts/models/member_status.py`
- `lca/contracts/models/memory.py`
- `lca/contracts/models/message.py`
- `lca/contracts/models/partial_buffer.py`
- `lca/contracts/models/perceive_state.py`
- `lca/contracts/models/perception.py`
- `lca/contracts/models/plan_ref.py`
- `lca/contracts/models/plane.py`
- `lca/contracts/models/preinstall.py`
- `lca/contracts/models/result.py`
- `lca/contracts/models/role_status_rules.py`
- ... 共 42 个
