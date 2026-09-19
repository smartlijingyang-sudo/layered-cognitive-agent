# Agent Note: ADR-0244 认知记忆闭环、上下文会话流与执行沙箱根治落地

Status: implemented

## Problem

多轮会话失忆（每轮交互丢失前文）、主外层图拓扑绕过 reflect/remember、成功工作流无法沉淀为技能、沙箱缺少系统级 CJK 字体与工作区生命周期隔离、并发工具在观察面被覆盖、Doctor H7 步骤数启发式假阳性误报。这些缺陷要求从根因修复，而非针对测试打补丁。

## Decision

按 ADR-0244 六个阶段落地：

1. **上下文会话流**：前端 `executeGatewayRun.ts` 过滤占位符并按模型上下文窗口做组感知预算切片（`@lobechat/context-engine`）；后端经 `RunSessionWriterProtocol.seed_prior_turns` 把历史事实以 `historical: True` 单轨注入 Session，废除 `PRIOR_CONVERSATION_WM_KEY` 伪通道。
2. **主图闭环**：`bundles/outer/phase_main.yaml` 打通 `think(respond) → reflect → remember → terminal`，反射评分走纯内存规则（不额外调用 LLM）。
3. **观察面复数化**：`JournalStep` 原生支持 `tool_calls`/`tool_results` 复数与 `invocation_id`，Doctor H7 用 `journal_invs` 与 `spine_invs` 集合精准对账，废弃步骤数启发式。
4. **沙箱基线**：onlyboxes 镜像烤入系统级 `/etc/fonts/local.conf` CJK 回退；`WorkspaceService` 提供 `{home}/workspace/` 持久读写。
5. **声明式记忆**：`MemorySystem` 协议新增 `retrieve(manifest)`，三个实现（Simple/Temporal/Assistant）落地；`phase.perceive.memory_retrieve` 解析 canonical `memory` capability，`phase.perceive.fold` 把检索结果以 `kind="memory"` 并入 manifest。
6. **程序性沉淀**：`phase.reflect.score` 用通用元特征提取 `ProceduralMemoryCandidate`（无硬编码技能名/正则）；`lca-assistant-curator` 以被动 `RuntimeLifecycleSubscriber` 观察终态 run，提案并确认后经 `assistant.skill_overlay` 安装蒸馏技能。

## Alternatives considered

### 新增 `memory.retrieved` ItemKind

被拒。`kind="memory"` 已是闭集且 prompt 渲染器已消费，新增 kind 会波及所有 kind 消费者，无提示收益。

### 注册独立 `memory_provider` canonical capability

被拒。会与已组合的 `MemorySystem` 形成平行别名，违反 no-parallel-mechanism 规则。

### curator 自建调度循环

被拒。assistant 插件静态禁止 `asyncio.create_task`/定时器（I-A12），必须用被动 `RuntimeLifecycleSubscriber`。

## Consequences

- 第二轮提问能引用第一轮上下文；并发工具调用全部落盘进 `journal.json`。
- `memory_retrieve` 节点从死节点变为真实检索；`WorkspaceService` 替代占位 provider。
- 技能蒸馏由通用元特征驱动，图节点零硬编码；提案存于 run 目录，确认后写入 `{home}/skills/`。
- 已知后续项：Onlyboxes guest 侧工作区 staging/harvest 同步尚未实现（见 gap-closure plan Appendix C）。