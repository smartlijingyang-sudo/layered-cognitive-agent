# LCA ↔ LobeHub 定制清单

> **基准版本**：LobeHub v2.2.13。应用：`python3 deploy/lobehub/patch_lobehub.py apply --reset`

协议 SSOT：`docs/run-live.md`。

## 架构

```
Browser 发消息
  executeClientAgent（选择器只有 solo / team / auto）
    → runLcaJournal          POST /runs 一次 + 投影 + sealRow
    → finishLcaChat          停转圈 / 队列 / 通知（不是 AgentRuntime）
    → 一个说话人一条 assistant；工具卡写在当前 assistant.tools
```

Title / embeddings 仍走 `openai_shim`（`/v1/chat|embeddings|responses`），不进 Run。
不走 GeneralChatAgent / call_llm / call_tool。
未知模型（例如旧会话里的 `qwen3.7-plus`）在发送时 remap 成 `solo`。

## 允许存在的补丁

| 补丁 | 级 | 存在理由 |
|---|---|---|
| `lca_run_driver` | A | 拷贝 TS 投影器 + 生成 `lcaWire.ts`；短路进 `runLcaJournal` / `finishLcaChat` |
| `file_proxy_rewrite` | A | 浏览器要拿产物；rewrite `/files`、`/lca-api/runs` |
| `sandbox_generated_files` | B | 上游 ExecuteCode 卡片不渲染 `state.files` |
| `default_model` | C | 默认模型必须是 `solo` |
| `lca_model_catalog` | A | 选择器只暴露 solo / team / auto，屏蔽厂商模型 |
| `openai_guard` | B | 标题等小请求仍走 model-runtime，防止 `solo` 进 Responses |
| `dev_auth_*` / `lan_dev` / `topic_route` | D | 开发体验 / 路由，与 Run 协议无关 |

不要再给 `StreamingHandler`、`ClientLLMTransport`、`GeneralChatAgent`、`Reasoning.tsx` 打补丁。
