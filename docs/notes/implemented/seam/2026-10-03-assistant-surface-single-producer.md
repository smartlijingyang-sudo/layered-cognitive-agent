# Agent Note: surface/assistant_message 由 think.llm.persist 独家写入

Status: implemented

## Problem

`surface/assistant_message` 有两个生产者，一次 LLM 响应各写一行。Session 是仅追加日志，两行都留下。`RunSessionWriter.derive_messages` 把 surface 事件逐条投影成 wire 消息，于是模型每一轮都看到自己的上一条回复两次，两份 `tool_calls` 声明同一个 `call_id`。

模型把双份历史当成范例。它在一次连续输出里把自己的话写两遍，重复边界落在单个 SSE delta 内部（`run_56c3352cd22e`：token `seq` 0→13 单调递增，delta 原文是 `内容：\n\n\n\n文件`），所以任何重试或二次拼接都解释不了。双份文本再被写回历史，下一轮范例更强。`run_f70ccf932e9d` 连续 16 轮全双写，用户看到的是 24 次重复追问。

## Decision

`think.llm.persist` 是 `surface/assistant_message` 的唯一生产者。它从 typed runtime carrier 取 writer，缺 writer 抛 `TypeError`；它在 think 子图里每轮只有一个位置，`state.step` 就是它写入的 turn/step。

`ModelVisibleHookAdapter` 只发 catalog 事实（`model.completed.v1` / `assistant.responded.v1`）和 spine payload（`SpineLlmRequestHeaderAssistantPayload`）。它是观察面装饰器，不解析 Session，不构造 writer。`complete_model` 自带 Session 未绑定即返回的守卫，装饰器不再自行查 `resolve_session_reader`。

失败语义不变。`llm.persist` 的 writer 缺席是 fail-loud；装饰器侧 hook 抛错仍按 L10 + D5 吞掉，不挡业务。时序上 assistant 行仍在任何工具执行之前落盘，`effect.execute` 继续依赖 think 侧已写好 assistant 行再补对应的 `surface/tool_result`，persist-before-execute 与 orphan-drop 语义都不变。

外部后果：模型可见历史里每轮 assistant 只出现一次，`arguments` 只有一种形状（`NativeToolCall.arguments` 的 dict，由 `openai_compat/history` 在 wire 边界序列化成 JSON 字符串）。

## Alternatives considered

### 为什么不留装饰器、删图节点？

装饰器要拿到 writer 只能查 `resolve_session_reader()` 这个读面 ContextVar，再 cast 成 `SessionProtocol`。ADR-0226 §1 明确要求 writer 构造注入，禁止 ContextVar 查找与静默 None。它还会对任何经过 instrumented Brain 的调用触发，包括不传 cursor 的旁路调用，而 turn/step 身份只有图节点从 `state` 拿得到。留它就保留了这两个偏差。

### 为什么不在 derive_messages 去重？

去重让投影承担事实层的职责，违反 C4 与 C7。Session 里仍有两行同 `call_id` 的 assistant 事实，token 统计、fold、transcript 导出各自还要再判一次。投影可重建，事实不可修补。

### 为什么不做任何事？

重复会自我强化。历史里每多一轮，范例就多一份，模型继续双写，`derive_messages` 的长度按两倍增长，同一份 prompt token 翻倍计费。

## Consequences

`BodySurfaceEventContract` 声明的「exactly 1 `surface/assistant_message`」现在由测试守护，此前只有文档表述。`append_tool_result` 有三个生产者（`effect.execute`、`loop.commit.tool_journal`、无调用方的 `simple_body`），受 ADR-0201 single-append 约束，当前活跃路径只走 `effect.execute`（live 行带它的 source marker），本次不动。`bundles/concept/llm_dispatch.yaml` 声明的 `factory: llm.call` 已无对应 provider，且无任何 bundle 或 profile 引用，属独立的死配置。

## Verification

`tests/integration/test_assistant_surface_single_producer.py`：

- 观察面单独跑一轮 streamed 响应，Session 里 `surface/assistant_message` 为 0 行；断言前先钉住 `capture_post_llm` 真的被调过，因为 hook 会吞掉 post-emit 异常，否则「没有行」可能是假证据。
- 两条腿按组合顺序跑同一份响应，恰好 1 行，且该行声明的 `call_id` 完整。
- 连跑两轮后 `derive_messages()` 里不存在相邻且 `tool_calls` id 相同的 assistant 对。
- 结构锁：装饰器模块源码不含 `append_assistant_message`，与 `test_persist_module_has_no_tool_journal_commit_reference` 同类。

四个测试在修复前分别报 2 行、`roles=['assistant', 'assistant', 'assistant', 'assistant']` 与结构锁命中，修复后全绿。

## Cross-references

- 契约：[lca/contracts/cognition/body/executor/contracts.py](../../../../lca/contracts/cognition/body/executor/contracts.py)
- ADR：[docs/adr/0226-session-write-path-collapse.md](../../../adr/0226-session-write-path-collapse.md) §1（writer 注入，禁 ContextVar）与 §3（当时把 surface emit 交给 adapter hook，本 Note 将该点收归图节点）
- 前序 Note：[2026-09-15-pr2-write-path-refactor.md](2026-09-15-pr2-write-path-refactor.md)
- 证据 run：`run_56c3352cd22e`、`run_f70ccf932e9d`、`run_58bdfa61d4ee`、`run_ea0f17cac222`、`run_e68917adcf9a`
