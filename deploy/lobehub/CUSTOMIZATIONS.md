# LCA ↔ LobeHub 定制清单

> **基准版本**：LobeHub v2.2.13。应用：`python3 deploy/lobehub/patch_lobehub.py apply --reset`

协议 SSOT：`docs/superpowers/specs/2026-08-13-run-live-architecture-design.md` 与 `docs/run-live.md`。

## 架构

```
Browser
  └─ JournalTransport          唯一 LCA 生产入口
       POST /lca-api/runs      → gateway POST /runs
       GET  /lca-api/runs/id/live → Journal SSE
            │
            ▼
       StreamingHandler        上游，不改
            │
            ▼
       Thinking / 工具卡 / 正文
```

Title / embeddings 仍走 `openai_shim`（`/v1/chat|embeddings|responses`），不进 Run。

## 允许存在的补丁（spec §5.2）

| 补丁 | 级 | 存在理由 |
|---|---|---|
| `journal_transport` | A | 订 Journal live，喂 StreamingHandler |
| `call_llm_finalizer` | A | 上游没有「服务端已跑完工具」开关 |
| `file_proxy_rewrite` | A | 浏览器要拿产物；rewrite `/files`、`/lca-api/runs` |
| `sandbox_generated_files` | B | 上游 ExecuteCode 卡片不渲染 `state.files` |
| `default_model` | C | 默认模型必须是 `solo` |
| `openai_guard` | B | 标题等小请求仍走 model-runtime，防止 `solo` 进 Responses |
| `dev_auth_*` / `lan_dev` / `topic_route` | D | 开发体验 / 路由，与 Run 协议无关 |

已删除：`agent_timeline_transport`、整个 `patches/streaming/`（`lca.events` / `openai_stream` 时代）。

不要再给 `StreamingHandler`、`ClientLLMTransport`、`Reasoning.tsx` 打补丁。
