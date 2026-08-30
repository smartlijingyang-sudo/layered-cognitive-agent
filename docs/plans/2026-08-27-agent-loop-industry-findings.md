# Agent Loop 行业实践要点（2026-08-27）

本记录仅用于本次 Agent Loop 主链审查与实施选型；结论以当前仓库代码和相关 ADR 为准。

| 来源 | 官方要点 | 对 LCA 的直接含义 |
|---|---|---|
| LangGraph Interrupts | 中断暂停时需要持久化检查点与稳定线程标识；以 `Command(resume=...)` 恢复相同执行线程；中断前的副作用必须幂等。 | 人工审批与恢复必须由稳定 session 标识、可重建 cursor/checkpoint 和 command 驱动，不能依赖旧进程内 runnable。 |
| OpenAI Agents SDK HITL | 需审批工具会产生 run-level interruption；批准或拒绝后在保留的运行状态上恢复；文档特别讨论长期待审批和 pending task versioning。 | 审批是 runtime/session 层能力，而不是某一个 executor 的异常分支；必须在 session 投影中可见并支持可验证恢复。 |
| Temporal Activity Definition | 可重试执行单元必须设计为幂等；活动可能整体重新执行，应该以更细粒度的原子单元隔离副作用。 | LCA 的 phase retry 只能重试无副作用阶段，或经强制幂等 effect gateway 执行；重试策略需要由执行节点显式声明并对审计事实完整记录。 |

## 选型结论

当前 HEAD 的 `Session Spine` 已能通过 `SessionActivator` 从 durable session 事实重建 LiveAgent，并由 `CommandGateway` 传递审批恢复命令；与此同时，`gateway/runs/lifecycle.py` 的 legacy `/runs` 路径仍把 `outcome.resumable` 保存为 `RunSession.runnable`，恢复时直接调用 `session.runnable.resume(...)`。该分叉使进程重启后的 HIL 恢复不具备与 Session Spine 相同的可靠语义。

本次优先将 `/runs` owner 切换为已有的 command-backed `SessionRunAdapter`，以插件化的 `run_owner` 选择 seam 代替 handler 内部产品分支。这样既移除 legacy 的 live-object resume 依赖，也不改变六阶段认知闭环或重复实现 Session Spine。

## References

[1]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph Interrupts"
[2]: https://openai.github.io/openai-agents-python/human_in_the_loop/ "OpenAI Agents SDK — Human-in-the-loop"
[3]: https://docs.temporal.io/activity-definition "Temporal — Activity Definition"
