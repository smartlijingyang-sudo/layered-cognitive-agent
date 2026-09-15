# lca.plugins.think

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
Think phase 插件。提供 critic / synthesizer 的 null 默认实现（无副作用、可降级）。

## 2. 不负责
- 推理逻辑（由 lca.cognition.brain 提供）
- Tool 执行
- Plan 编排

## 3. 输入
- Critic 输入：`Decision` 对象（由 lca.cognition.brain.synthesizer 产出）
- Synthesizer 输入：多 `Result` 候选列表

## 4. 输出
- `null_critic.py` 提供 `NullCritic` — 总是 `ALLOW` verdict
- `null_synthesizer.py` 提供 `NullSynthesizer` — 选第一个 candidate 直接返回

## 5. 允许依赖

lca.contracts, lca.harness, lca.cognition, lca.infrastructure, lca.plugins, lca.application
（与 pyproject `[tool.lca.package_contracts.lca.plugins.think].allowed_dependencies` 镜像；
现状 import 计数 56 / 8 / 5 / 2 / 1 / 1。）

## 6. 禁止依赖

lca.agent, lca.session, lca.loop, lca.nodes, gateway
（当前对这四者的 import 数为 0；`gateway/` 顶层包已迁入 `lca/*`，保留为回归哨兵。）

## 7. 副作用
llm:call, log:emit

## 8. 失败语义
- Critic / Synthesizer 永远不失败（null 实现）
- 上游异常透传

## 9. 公共入口

包门面不重导出符号（模块级列表为空）。按 provider 路径取用：
cognitive、composition、loop、null、reasoner、system 与 role profile 模块；
装配以 bundle 的 `$module` 路径为准。
