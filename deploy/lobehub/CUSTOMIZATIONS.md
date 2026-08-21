# LCA ↔ LobeHub 定制清单

> **基准版本**：LobeHub v2.2.13。应用：`python3 deploy/lobehub/patch_lobehub.py apply --reset`

协议 SSOT：`docs/specs/run-live.md`。

## 架构

```
Browser 发消息
  executeClientAgent（选择器只有 solo / team / auto）
    → runLcaJournal          POST /runs 一次 + 投影成原生消息图 + seal
    → finishLcaChat          停转圈 / 队列 / 通知（不是 AgentRuntime）
    → 一次 LlmCallStarted = 一条 assistant；每个工具一条 role=tool 子消息（result_msg_id）
```

Title / embeddings 仍走 `openai_shim`（`/v1/chat|embeddings|responses`），不进 Run。
不走 GeneralChatAgent / call_llm / call_tool。
未知模型（例如旧会话里的 `qwen3.7-plus`）在发送时 remap 成 `solo`。

## 允许存在的补丁

| 补丁 | 级 | 存在理由 |
|---|---|---|
| `lca_run_driver` | A | 拷贝 TS 投影器 + 生成 `lcaWire.ts`；Journal → 原生 assistant/tool 图 |
| `office_preview_local` | A | 本地 Office 产物走下载，不喂 officeapps.live.com |
| `file_list_gateway_preview` | A | 组级 FileListViewer 对 `/files` 走 URL 预览，不进 LobeHub file-store |
| `file_proxy_rewrite` | A | 浏览器要拿产物；rewrite `/files`、`/lca-api/runs`、presence/console |
| `default_model` | C | 默认模型必须是 `solo` |
| `lca_model_catalog` | A | 选择器只暴露 solo / team / auto / creator，屏蔽厂商模型 |
| `openai_guard` | B | 标题等小请求仍走 model-runtime，防止 `solo` 进 Responses |
| `host_console` | D | 本机 host sidecar 终端投影；不是 Run |
| `execution_target` | C | 执行环境：用电脑 / 用 DSH / 云沙箱 / 自动；去掉无设备与下载桌面 |

不要再给 `StreamingHandler`、`ClientLLMTransport`、`GeneralChatAgent`、`Reasoning.tsx` 打补丁。
