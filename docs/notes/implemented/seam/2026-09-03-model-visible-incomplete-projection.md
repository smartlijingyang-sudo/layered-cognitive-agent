# Agent Note: model_visible 投影丢三件事

Status: implemented

> **Superseded by**: [观测面 SSOT 全量收口与约束保证](../seam/2026-09-03-observation-ssot-registry.md)(root note, implemented 2026-09-03)。本 note 作为 BUG 现场诊断证据保留;修法已并入根 note PR-1~7。

## Problem

`lca.infrastructure.observability.loop_cursor.model_visible_capture` 写 `<run_dir>/model_visible/<step_id>/{tools,messages,manifest}.json`,理论上承担"模型可见输入 + 工具 schema + 消息序列"的可重建证据。当前三处缺口让 debug agent 在 `journal replay --diff-only` 与前端 viewer 上**永远看不到模型思考、工具调用、工具结果**:

1. **assistant 回复没投影**。`messages[].role` 永远是 `user`,从不出现 `assistant` / `tool`;清单长度固定为 1(单一 user 消息),LLM 回复内容、`tool_calls`、function_call 都不在。
2. **`tools.json` 是空 dict 列表**。22 条 tools 序列化成 `{}`(原数组里 `entry == {}`),从 `tools.json` 看不到 LLM 实际能调的工具名 / 参数 schema。
3. **错误归类 user role**:某些上层 reasoner / adapter 把 system 模板错塞到 `messages[0]`(role=user),capture 把它原样落盘。debug agent 看到 user 消息里有 system prompt 模板,会误判"system 注入失败",其实是上游 reasoner 错配。

证据来源:

- `traces/runs/run_365ad8d3c2c0/model_visible/step-001/`:
  - `messages.json`:`messages_overview.keys() = ['system']`(缺 `user` / `assistant` / `tool` overview),`messages[0].role='user'` 且 `content` 是 lobe-cloud-sandbox system 模板,`messages[].len() == 1`。
  - `tools.json`:22 个 `{}`,keys 空。
- spine SSOT 同一 run 里 `step.tool_call.record` × 2、`body.tool.execute.end` outcome=success × 2;**LLM 实际调过 bash 工具且成功**,但 model_visible 投影里看不到任何工具名 / 调用参数 / 返回值。
- 根因代码位置:
  - `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py:285`:`capture.capture(...)` 在 `await self._inner.complete(prompt=prompt, **kwargs)` **之前**调用(读 `kwargs['messages']`,这是 LLM 调用前的消息序列,不含 assistant 回复)。
  - `_to_jsonable`(`lca/infrastructure/observability/loop_cursor/_capture_io.py:33`)对工具 schema 实例走 `dataclasses.asdict` / `to_dict` / `model_dump` / `__dict__` / `repr` 5 段回退,落到 `repr()` 时被 `json.dumps` 序列化为 `{}`(因为 `repr` 返回的字符串可能是 `<lobe_cloud_sandbox.ComputerTool object at 0x...>`,该 repr 字符串被进一步 dict 序列化时又走一次 `_to_jsonable`,碰到非 JSON 类型回退 `{}`)。

debug agent 的"对话轨迹 viewer / `journal replay --diff-only` 截图"严重依赖这三个文件;**当前不能重建"模型看到了什么、说了什么、工具被怎么调"**,违反 ADR-0169 D7 / ADR-0176 D4 "model_visible 是 LLM 真实输入的可重建投影"。

## Proposal

分三段独立但一起发的契约改动:

1. **post-call capture 点**。在 `model_visible_llm_adapter.stream()` 里 yield 完最后一个事件(或 `complete()` await 完后),再调一次 `capture.capture(...)`,把 LLM 实际产出(assistant content / tool_calls / finish_reason / usage)合并入 `messages[]`。Protocol `ModelVisibleArtifact` 增加 `messages_after_assistant: list[Any] | None` 字段(可选)或扩展 `messages` 字段为"调用前 + 调用后"的拼接列表,带 `phase: pre|post` 标记。
2. **tools schema 序列化**。在 `_to_jsonable` 增加优先级 0:`getattr(value, 'openai_schema', None)` / `getattr(value, 'anthropic_schema', None)` / `getattr(value, 'tool_schema', None)` 三选一(按 LLM Provider 惯例),把工具实例转成可直接发 LLM 的 JSON Schema 形式。落盘后 `tools.json` 应是 `[{name, description, parameters: {type, properties, required}}, ...]`。
3. **错误归类探测**。在 capture 末尾加一道 sanity check:若 `messages[0].role == 'user'` 且 `content` 包含 `<tool name=` 或 `ROLE:` 等 system 标记,在 manifest.json 里加 `capture_warnings: [{kind: 'system_misrouted_to_user', step_index: N}]`,让 debug agent 知道这是上游问题,不是 capture 问题。

## Wire contract

新增 / 修改字段:

- `messages.json` → 新增 `messages_after_assistant: list[dict]` 字段,每个元素 role ∈ {`assistant`, `tool`},含 `content` / `tool_calls` / `tool_call_id`。
- `tools.json` → 元素 schema:`{name: str, parameters: dict, description: str | None}`(JSON Schema)。
- `manifest.json.body.capture_warnings: list[{kind, step_index, detail}]`。
- `ModelVisibleCapture.capture(...)` Protocol 增 `assistant_messages: list[Any] | None = None` 入参(向后兼容,默认 None 走旧路径)。
- `_to_jsonable` 优先级:1 → `provider_schema()` 方法;2 → `to_dict` / `model_dump`;3 → `dataclasses.asdict`;4 → `__dict__`;5 → `repr` 字符串(用 `__repr_value__` 哨兵防 json round-trip)。

## Alternatives considered

### Why not 在 LLM 适配器之后,改 Brain 边界写 model_visible?

Brain 边界没有"模型完整消息序列"的可观察性(那是 Reasoner / LLM adapter 之间的产物)。改 Brain 等于把"model-visible" 概念从 LLM 边界搬到 Brain 边界,违反 ADR-0169 D7 的"以 LLM adapter 边界为 SSOT 投影点"。

### Why not 直接让 messages 包含 streaming 累计?

Streaming 累计丢失"assistant message"的边界 — 工具调用与文本回复穿插时难以分辨单一 assistant turn。最干净是 `messages_after_assistant` 列表,与调用前 `messages` 平行,view 层按时间顺序渲染。

### Why not 把 tools schema 序列化挪到 LLM Resolver 装配时一次性算好缓存?

不行。LobeHub lobe-cloud-sandbox 这种工具 schema 包含私有字段 / 闭包 / 服务地址,必须在 capture 时按 tool 实例现抓(provider 是后注入的);缓存会错过 profile patch 后注入的工具。

## Acceptance criteria

- 给定 `traces/runs/run_365ad8d3c2c0/`,`model_visible/step-001/messages.json` 应包含至少 3 条 `messages`:role=user(原始 prompt) / role=assistant(LLM 回复,含至少 1 个 `tool_calls`) / role=tool(工具返回)。
- `tools.json` 22 个元素全部含 `name` 字段非空、`parameters.type == 'object'`。
- `journal replay --diff-only run_365ad8d3c2c0 --step 1` 输出包含 assistant content 段。

## Risks

- 改 `_to_jsonable` 优先级顺序会影响其他 caller(loop_cursor / journal step / projection_host);同 PR 需把那些 caller 的 `_to_jsonable` 也改用同一个 helper,避免双轨。
- `messages_after_assistant` 双写(调用前+调用后)会让 `messages.json` 体积变大;若已超 4 KiB sidecar 阈值会触发 exception 路径(见 ADR-2026-09-03 traceback-ssot-hook),需要在 capture 入口加 size check 提前 sidecar。
- `system_misrouted_to_user` 警告会暴露上游 reasoner bug,可能被一些 viewer 当作 error 高亮 — 需要在 viewer 端把 `capture_warnings` 与真 error 分通道渲染。

## Related

- `lca/infrastructure/observability/adapters/model_visible_llm_adapter.py` — capture 调用点,需增加 yield-after-capture。
- `lca/infrastructure/observability/loop_cursor/model_visible_capture.py` — Protocol 与实现,需扩 `assistant_messages` 入参。
- `lca/infrastructure/observability/loop_cursor/_capture_io.py:33` — `to_jsonable` 优先级需重排。
- `lca/infrastructure/tools/lca_computer/manifest.py` — lobe-cloud-sandbox 工具实例的 schema 来源。
- ADR-0169 D7 / ADR-0176 D4 — model_visible SSOT 语义。