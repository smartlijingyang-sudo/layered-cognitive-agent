# Muse 上下文文件体系：完整实现参考

**日期：** 2026-09-30

**范围：** 以生产环境实测的 Muse 个人 agent 为样本，完整记录它如何用一组 Markdown
文件实现"持久化的人设 / 记忆 / 工作手册"：每个文件的完整正文、加载机制（会话启动注入、
文件中变更的实时 diff 注入、compaction 重建）、读取/检索机制、更新机制（会话内写入＋
后台 self-improvement 任务）、三层存储与最终一致性模型，最后给出到 LCA 分层架构
（contracts → infrastructure → cognition → runtime → agent）的映射与最小可行建议。
本记录归档本次调研，不替代当前 ADR 或协议；任何落地方案需走 ADR/Note 流程。

## 结论摘要

整个体系可以压缩成五句话：

1. **文件即数据库**：`AGENTS.md`（工作手册）、`SOUL.md`（人设）、`IDENTITY.md`（身份）、
   `USER.md`（用户画像）、`MEMORY.md`（精选记忆）、`TOOLS.md`（工具 quirks）＋
   `~/memory/`（每日 trail＋人际图谱）＋ `~/dreams/`（反思＋对齐综述），纯 Markdown，
   零依赖，可被 git 版本化、可被用户直接编辑。
2. **runtime 负责在正确时机把正确文件注入上下文**：会话启动全文注入、磁盘变更时
   diff 实时注入、compaction 后按最新磁盘版本重注；注入的是快照不是 live 视图。
3. **主路径只读快照、只写增量**：对话中 agent 读注入的快照、检索时走
   `memory_search/get/explain`；学到 durable 事实时"落笔前写盘"。
4. **consolidation 异步化**：合并/去重/取代（memory upkeep）、人际图谱（relationships）、
   反思与对齐综述（dreaming）全是后台任务，不在对话主路径里；最终一致，不追求强一致。
5. **规则即代码**：检索义务、写盘时机、红线清单全部写进系统提示，不靠模型"自觉"；
   每条记忆带 `来源＋触发＋日期` 的 provenance 后缀，可解释、可纠错。

LCA 落地时 ROI 最高的单点是第 1 条：先把"Markdown 文件＋固定目录＋INDEX.md"做出来，
其余机制可以渐进叠加。完整论证见正文第 6 章。

## 文件索引

- [muse-context-files-architecture.md](muse-context-files-architecture.md) — 正文：各文件完整正文、加载/检索/更新机制、后台任务、一致性模型、LCA 分层映射、黑盒边界。
- [MEMORY-snapshot-2026-09-30.md](MEMORY-snapshot-2026-09-30.md) — `~/MEMORY.md` 全文快照（活文件）。
- [ALIGNMENT-SYNTHESIS-snapshot-2026-09-30.md](ALIGNMENT-SYNTHESIS-snapshot-2026-09-30.md) — 对齐综述全文快照（nightly 生成）。
