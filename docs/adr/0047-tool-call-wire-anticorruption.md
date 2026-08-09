# ADR-0047: 工具调用 Wire 防腐 —— finish_reason + 三态 Outcome + 执行闸门

## 状态

Accepted

## 背景

LLM function-calling 的 `arguments` 是不可信 wire 字符串。长 `run_sandbox_code`
参数 + thinking + `max_tokens` 时常被截断，表现为：

```text
JSONDecodeError: Unterminated string starting at: line 1 column 10 (char 9)
```

此前适配器在 `build_llm_response` 内对 `arguments_json` 直接 `json.loads`，
异常穿透 cognitive loop → `unexpected_loop_error` → run FAILED。

临时止血曾「静默补全 JSON 后执行」或「降级为 respond」——前者假完整、
后者错误收口（`DefaultStopOutcomePolicy` 对 `respond` 倾向停止）。

这与框架原则冲突：

- ADR-0002 / ADR-0045：外部形态在**边界**归一，内部只见规范决策
- 工具失败应是 **Observation(success=False)** 回灌 loop，而非 abort 或对用户 respond

### 业界对照

| 来源 | 做法 |
|---|---|
| OpenAI Chat Completions | `finish_reason=length` 表示输出不完整 |
| OpenAI Responses | `status=incomplete` + `incomplete_details.reason` |
| Agent 框架 | partial tool call → 错误观测，禁止当完整调用执行 |

## 决定

### 一、契约：`FinishReason` + `LLMResponse.finish_reason`

归一化 provider 结束信号（`stop` / `length` / `tool_calls` / …）。
`LENGTH` 与 tool_call 并存时，arguments **一律 Incomplete**。

### 二、L0 纯模块 `tool_arguments.py`：三态 Outcome

```
Ok(arguments) | Incomplete(raw, reason) | Invalid(raw, error)
```

- 只解析、分类，**不执行、不 respond、不静默修完就跑**
- `JSONDecodeError` → Incomplete（截断信号），永不抛出

### 三、`build_llm_response` 编码规范 Decision 载荷

| Outcome | 编码 |
|---|---|
| Ok | `use_tool` + 真 arguments + `tool_wire_status=ok` |
| Incomplete / Invalid | 仍 `use_tool` + 保留 `tool_name` + `arguments={}` + `tool_wire_*` 字段 |

**禁止**降级为 `respond`。

### 四、Parser → `Decision.extra`；Body 闸门软失败

- `SimpleDecisionParser` 将 `tool_wire_*` 迁入 `Decision.extra`，blocking 时清空 arguments
- `UseToolOperation`：status ∈ {incomplete, invalid} →  
  `Observation(success=False, failure_kind=tool_wire)`，**不调 sandbox**
- Stop 策略：`use_tool` + 失败 → 不停止 → 下一轮 think 可缩短重试

### 五、有 tools 时抬高默认 `max_tokens`

`DEFAULT_MAX_TOKENS_WITH_TOOLS = 8192`（仅当 settings 仍为默认 4096 且调用方未覆盖）。  
降低截断概率；**不替代** Incomplete 闸门。

## 模块边界

| 模块 | 职责 |
|---|---|
| `contracts` FinishReason / semantic_keys | 契约 |
| `llm_adapter/tool_arguments.py` | 纯解析三态 |
| `openai_compat/_shared.py` | Outcome → Decision JSON |
| `_chat_completions` / `_responses` | 抽取 finish_reason |
| `decision_parser` | wire 字段 → Decision.extra |
| `UseToolOperation` | 执行前闸门 |

## 后果

- 正面：截断不再杀 run；agent 可见机读失败并重试；与 ADR-0045 ACL 对称
- 负面：`finish_reason=length` 时即使 JSON 碰巧可 parse 也拒绝执行（偏安全）
- 中性：长代码仍建议拆步或写文件再跑（产品契约，非本 ADR 强制）

## 非目标

- JSON Schema constrained decoding
- 强制 `write_file` → `run path` 工具拆分
- 前端专用投影（既有 tool 失败路径即可）
