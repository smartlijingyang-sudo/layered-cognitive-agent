# lca/harness/projection

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
Reducer 状态 fold 镜像（AGENTS.md C12）：`AgentStateProjection` 从 Session
事件流纯函数重建 `AgentState`，与 reducer `apply_*` 同步。客户端投影面归
`lca/plugins/session/projection_registry`（DSH session-projection 对齐）。

## 2. 不负责
投影注册表与驱动（归 `lca/plugins/session/projection_registry`）；web 视图
单元（已退役，被新投影家族单元取代）。

## 3. 输入
- 当前包内 `1` 个公开模块 + `1` 个公开符号（class）

## 4. 输出
- 暴露的公共 API：1 个显式 __all__ 条目（`AgentStateProjection`）

## 5. 允许依赖
- `lca.contracts`

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.harness.projection].forbidden_dependencies`**:

- `lca.agent`
- `lca.application`
- `lca.cognition`
- `lca.runtime`

## 7. 副作用
无（纯函数 fold）。

## 8. 失败语义
fold 输入必须是合法 Session 事件流；非法事件形态抛 `ValueError`。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `AgentStateProjection`

**模块清单**:

- `lca/harness/projection/agent_state.py`
