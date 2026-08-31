# lca.plugins.bundles

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
Bundle 组合 —— 把多个 plugin 装成一个可装载单元。coding_agent_tools 提供 Coding Agent 所需全套工具（bash / file_write / trace_inspector 等）。

## 2. 不负责
- 单个工具的实现细节（由 lca.plugins.tools.* 提供）
- 工具编排（由 Profile / Bundle 装配期决定）

## 3. 输入
- Profile 解析出的 bundle 配置（per ADR-0065 §六）

## 4. 输出
- `coding_agent_tools.py` 提供 `lca-coding-agent-tools-bundle` —— 注册一组 Coding Agent 默认工具

## 5. 允许依赖
lca.contracts, lca.plugins

## 6. 禁止依赖
gateway

## 7. 副作用
log:emit

## 8. 失败语义
- 单个工具注册失败 → 整 bundle 拒绝加载
- 重复注册 → Idempotency 保护（已注册的跳过）

## 9. 公共入口
由子模块 setup 函数注册；无显式 `__all__`（plugin 自描述）。