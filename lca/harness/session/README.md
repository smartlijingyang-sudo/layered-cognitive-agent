# lca/harness/session

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
跨平面共享的 Session 纯工具：`emit` —— typed session 事件对象 →
`Session.append` 的统一发射出口。Session 事件真值层归 `lca/plugins/session`（ADR-0186）。

## 2. 不负责
事件落盘、恢复、投影（归 `lca/plugins/session` 家族）；词表注册（归
`lca/contracts/harness/memory/events.py`）。

## 3. 输入
- 当前包内 `1` 个公开模块 + `1` 个公开符号（function）

## 4. 输出
- 暴露的公共 API：1 个显式 __all__ 条目（`emit`）

## 5. 允许依赖
- `lca.contracts`
- `lca_kernel.events`

## 6. 禁止依赖
**pyproject.toml `[tool.lca.package_contracts.lca.harness.session].forbidden_dependencies`**:

- `lca.agent`
- `lca.application`
- `lca.cognition`
- `lca.runtime`

## 7. 副作用
无（`emit` 委托 `Session.append`，副作用归调用目标）。

## 8. 失败语义
词表未注册 / 数据不可 JSON 序列化 → 发射点抛错（`Session.append` 契约）；
`SessionReentryError` 由实现层在嵌套 append 时抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `emit`

**模块清单**:

- `lca/harness/session/emit.py`
