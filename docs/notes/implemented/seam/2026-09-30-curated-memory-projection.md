# Agent Note: 结构化记忆的人可读投影

Status: implemented

## Problem

助理记下的事实躺在 `memory/semantic.json` 里。人打开助理主目录看不到一份可读的长期记忆。会话变长以后，装配如果从末尾截断，工作手册会把刚写入的记忆挤出提示。模型也可以在写盘失败时对用户说已经记下。

## Decision

`AssistantMemory` 在语义层写入成功后，用活跃的 fact 与 preference 记录重写 `{home}/MEMORY.md`。身份记录仍只回填 `USER.md`。`memory/semantic.json` 继续是记录真值。`MEMORY.md` 页首写明它是投影，下次写入会整文件替换。

凭证形态的正文不落记录，也不改投影。写盘用同目录临时文件替换。失败时 `last_curated_receipt.ok` 为 false，已写入的 JSON 记录保留。

`memory.write.dispatch` 把这次提交的字节数和 `may_acknowledge` 打进 `MemoryReceipt`。`may_acknowledge` 仅在回执成功、字节数大于 0、且这次提交有记录编号时为 true。`guard_memory_claim` 在该标志为 false 时，把「已记下」一类句子换成明确的未写入说明。`think.decision.parse` 是认领守卫的消费点：节点运行时视图从 memory 能力动态读取 `last_curated_receipt`，`may_acknowledge` 为 false 时替换最终回复。守卫同时接受 `MemoryReceipt` 与 `CuratedProjectionReceipt` 两种回执形状；运行时没有回执时保持原文。

`persona_from_home` 每次从磁盘读取 `SOUL.md`、`USER.md`、`MEMORY.md`、`AGENTS.md`、`TOOLS.md`，按这个顺序装进有界的 backstory。后面还有文件时，当前文件最多使用剩余预算的一半。`rehydrate_after_compaction` 先丢掉历史里的旧注入块，再接上刚读到的常驻文件。历史在预算不够时从前面被切掉。

`think.reason.render` 每轮渲染前通过注入的 `standing_refresher` 重读磁盘上的常驻文件，刷新 `role_profile.backstory`。`refresh_standing_backstory` 位于 `lca/infrastructure/memory/standing_refresh.py`，由 `DeclarativeRuntimeBindings` 注入节点运行时。没有 home 绑定、没有 refresher、或读取失败时，原 profile 保持不变。这样压缩或外部编辑后的最新常驻文件在下一轮渲染进入 prompt。

## Alternatives considered

### 为什么不把 MEMORY.md 改成唯一真值？

那样要改掉 ADR-0247 的 `MemoryRecord` 和 ADR-0249 的语义落点。去重、取代和置信度会被迫从 Markdown 句子里解析。投影保留这些字段在记录里，句子只是渲染。

### 为什么不在这一切片做文件监听？

监听器的实现在参考系统里不可见。回合装配已经重读磁盘。等重读仍然把过期事实送进提示，再加监听。

### 为什么不把身份写进 SOUL.md 的 frontmatter？

ADR-0242 把身份放在 `profile.json`，人设放在 `SOUL.md`，并删除了 `IDENTITY.md`。

## Verification

`tests/cognition/memory/test_curated_memory_scenarios.py` 覆盖投影、取代、凭证拒绝、写盘失败、回执门闩、压缩后重读，以及 `memory.write.dispatch` 打上 `may_acknowledge`。流程级场景测试把「写盘 → 运行时视图回执 → 决策守卫 → 最终回复」串成一条链路：合法写盘保留「已记下」，凭证被拒替换为未写入说明。`tests/plugins/assistant/test_persona.py` 覆盖常驻文件预算。
