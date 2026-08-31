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
lca.contracts, lca.plugins

## 6. 禁止依赖
gateway

## 7. 副作用
llm:call, log:emit

## 8. 失败语义
- Critic / Synthesizer 永远不失败（null 实现）
- 上游异常透传

## 9. 公共入口
由子模块 setup 函数注册；无显式 `__all__`（plugin 自描述）。