# LobeHub UI 集成

用 LobeHub 官方 UI（v2.2.13）替换自研 `web/`，LCA Python 后端提供 OpenAI 兼容面。

## 架构

```text
Browser → LobeHub v2.2.13 (lobehub-ui/, bun run dev :3010)
              │ OpenAI client (OPENAI_PROXY_URL)
              ▼
LCA Gateway (:8765/v1/chat/completions)  ← gateway/openai_compat_api.py
              │
              ▼
LCA Agent/Team 运行时 (layer2~3)
```

默认聊天模型 `solo`（LCA 后端，`LLM_MODEL` / 百炼 Qwen）。全部请求走 LCA gateway：
- `POST /v1/chat/completions`：主聊天 + 系统 mini agent
- `POST /v1/embeddings`：代理上游 embedding
- `POST /v1/responses`：json_schema 结构化输出；普通 chat 回落 LCA run

联网搜索（ADR-0053）：`TAVILY_API_KEY` 已配 → `web_search`；否则 Qwen `enable_search` 兜底。

## 快速开始

```bash
./scripts/sync_lobehub_ui.sh          # 拉取 v2.2.13 到 lobehub-ui/
./scripts/start_lobehub_stack.sh dev  # 联合启动 gateway + LobeHub dev
```

环境模板：`deploy/lobehub/.env.lca` → 自动复制为 `lobehub-ui/.env`

## 目录说明

| 路径 | 说明 |
|---|---|
| `lobehub-ui/` | 官方 v2.2.13 源码（gitignore） |
| `.lobehub-upstream/` | 官方 git 克隆缓存（gitignore） |
| `scripts/sync_lobehub_ui.sh` | 拉取并 rsync 官方 release |
| `scripts/start_lobehub_stack.sh` | 联合启动编排 |
| `deploy/lobehub/.env.lca` | LobeHub 本地 env 模板 |
| `gateway/openai_compat_api.py` | OpenAI 兼容 HTTP 面 |
| `web/` | 原有自研前端（过渡期保留） |

升级：`LOBEHUB_RELEASE=v2.2.14 ./scripts/sync_lobehub_ui.sh`
