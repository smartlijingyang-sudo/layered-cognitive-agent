# Agent Note: Prompt section 只读 turn manifest，缺锚点显式可见

Status: implemented

## Problem

2026-09-17，`run_e204465f48d6`，用户问「今天有什么新闻吗」。perceive 的 clock sensor 产出 `2026-09-17 Thursday`，进了 manifest，也进了 think 子图的 `in_assembled_manifest`。模型收到的 system prompt 里没有 `CURRENT_DATE` 行。模型按训练截止先验补了年份，搜 `今日新闻 2025`。run 记为 completed，答案里的年份混着 2025 和 2026。

同一次渲染里，`USER_TASK`、`CONTEXT`、`<activated_skills>` 也全都不在。journal 的 `context_manifest` 为空，narrative 写「未携带 context_manifest（降级）」。也就是说，模型少了哪些段落，在观测面上和「本来就没有」长得一样。近 25 个 run 的 traces 里 `CURRENT_DATE` 一次都没出现。

## Decision

Section 的输入是这一轮的 typed 边界值：`role_profile`、`task`、`awareness`、`manifest`、`tools`、`activated_skills`。`StatefulSection.render` 的签名里没有 `AgentState`，`render_template` 也不接受它。要新事实就让它进 manifest，不能从 reducer 拥有的 state 上取。

clock 缺席时 `CURRENT_DATE: (未知当前时间)` 照常渲染，并在 section trace 上标 `used_fallback`。这一条修订 [cognitive-primitive-constitution-v3](../../../design/2026-08-19-cognitive-primitive-constitution-v3.md) D7 的「无 clock item 则删掉 `CURRENT_DATE` 行」：占位文本不是第二个时钟，它不读时间，只声明时间未知。D7 反对的是 Reasoner 私自 `now()`，这一条不违反。

`think.reason.render` 用 `current_manifest_from_state` 取 manifest（`state.perceive.manifest`）。`render_turn` 把 `ReasonerContext.manifest` 原样透传到 `ReasonerTurnRender.manifest`，`complete_turn` 再交给 `CurrentReasonerPrompt.context_manifest`，journal 的 `context_manifest` 由这一路供给。

`prior_conversation` section 从闭集删除（16 个 section）。历史由 `think.history.assemble` 经 session writer 走 messages。`ToolsSection` 里的 `prompt.surface.rendered` append 删除：纯渲染不写事实，而且它是 section 层对 `AgentState` 的最后一处依赖。

`render_template` 的 `registry` 和 `role_profile` 变成必填。`registry=None` 曾让整份 prompt 渲染成空串而调用方拿到 success，同一个坑以「registry 未接线」的形态出现过一次（见 `tests/concept/test_prompt_render.py` 的 budget_exceeded 回归）。

## Alternatives considered

### Why not 把 AgentState 传回 render？

改动最小，当天就能让日期回来。但 ADR-0220 把这条边界 typed 化就是为了阻止 section 越过 turn 读 reducer 拥有的字段；传回 state 等于把 `ReasonerContext` 的闭集契约作废，下一个 section 照样会去读 `working_memory`。代价是每次渲染都要重新界定「哪些 state 字段可读」，而这个界定没有机制守护。

### Why not 保持 D7 的「删行」？

删行本身不产生错误信息。这次 run 之所以以 completed 收场、之所以要靠人读 journal 才发现，就是因为少一行和本来没有一行在观测面上无法区分。占位文本让缺失出现在模型可见的 prompt 里，也出现在 section trace 里。代价是模型多看到一句「未知当前时间」，比它自己猜一个年份便宜。

### Why not 保留 prior_conversation section，改成从 manifest 读？

manifest 的 kind 闭集里没有会话历史，加一个就把同一份事实写成两条通道（messages 与 system prompt）。而且它的生产端写 `state.extra`、消费端读 `state.working_memory`，两边从来没接上过，`prior_turns` 从 gateway 一路运到 `RunSession` 就停了。代价是删掉后若要在 prompt 里重列历史，需要先决定它与 messages 的分工。

### Why not 把 prompt.surface.rendered 的 append 挪到 node 里？

node 有 `state`（因此有 step）也有 `turn_render`，但 `include_full_sandbox` 与 `digest` 只存在于 `PromptSurface.render_tools_block` 的返回值里，挪过去要么在 node 重渲染一次，要么给 `PromptTrace` 加两个只为审计存在的字段。而在真实渲染路径上 `tools=()`，`<tools>` 块本来就是空的，这条审计记录的内容会是 `tool_count=0`。代价是留下一个没有 emitter 的 catalog 事件（见 Consequences）。

## Consequences

模型每轮都拿到 `CURRENT_DATE`、`USER_TASK`、`CONTEXT`、`<activated_skills>`。clock 缺席时 prompt 上看得见。journal 的 `context_manifest` 有内容，narrative 的「未携带 context_manifest」不再出现。`lca/plugins/prompts/sections.py` 不再 import `lca.infrastructure`。

两处遗留，各自需要单独决定，本 note 不代为决定：

- `prompt.surface.rendered.v1` 仍在 catalog 与 `meta_event_taxonomy` 白名单里，已无 emitter。退役它是 C11 闭集改动，要走 ADR-0196 修订。
- `prior_turns` 仍从 transport 运到 `RunSession`，`run_context_factory` 仍把它写进 `RunContext.extra`，`runtime_loop` 仍拷进 `state.extra`，此后无消费者。多轮历史目前只经 session writer 的 messages 到达模型；这条 extra 通道要么接回 messages，要么删掉。

## Verification

`tests/scenario/prompt/test_prompt_assembler_integration.py` 驱动真实的 `think.reason.render` 节点与真实 registry，断言 `CURRENT_DATE: 2026-09-17 Thursday` 与 `USER_TASK` 出现在 prompt 里，断言 clock 缺席时渲染占位文本，断言 `turn_render.manifest` 就是 perceive 产出的那个对象。同文件对三个内置模板逐个参数化，断言每个都带日期锚点——`_builtin_section_refs` 用手维护的计数切片，模板可以无声丢掉一个 section。
