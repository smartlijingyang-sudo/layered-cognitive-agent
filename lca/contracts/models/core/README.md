# lca/contracts/models/core

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `25` 个公开模块 + `110` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：无 个显式 __all__ 条目； 110 个定义符号中，103 个为公共命名

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

- `lca/contracts/models/core/activation.py`
- `lca/contracts/models/core/approval.py`
- `lca/contracts/models/core/attachment.py`
- `lca/contracts/models/core/budget.py`
- `lca/contracts/models/core/conversation.py`
- `lca/contracts/models/core/decision.py`
- `lca/contracts/models/core/execution.py`
- `lca/contracts/models/core/gate_policy.py`
- `lca/contracts/models/core/guest_layout.py`
- `lca/contracts/models/core/lifecycle.py`
- `lca/contracts/models/core/llm.py`
- `lca/contracts/models/core/memory.py`
- `lca/contracts/models/core/message.py`
- `lca/contracts/models/core/perceive_state.py`
- `lca/contracts/models/core/perception.py`
- `lca/contracts/models/core/plane.py`
- `lca/contracts/models/core/preinstall.py`
- `lca/contracts/models/core/result.py`
- `lca/contracts/models/core/sandbox.py`
- `lca/contracts/models/core/sandbox_policy.py`
- `lca/contracts/models/core/state.py`
- `lca/contracts/models/core/stop.py`
- `lca/contracts/models/core/terminal_outcome.py`
- `lca/contracts/models/core/tool.py`
- `lca/contracts/models/core/workspace.py`
