# LobeHub UI 集成

用 LobeHub 官方 UI（v2.2.13）替换自研 `web/`，LCA Python 后端提供 OpenAI 兼容面。

## 架构

```text
Browser → LobeHub v2.2.13 (lobehub-ui/, bun run dev :3010)
              │ JournalTransport
              │ POST /lca-api/runs  →  POST /runs
              │ GET  /lca-api/runs/{id}/live
              ▼
LCA Gateway (:8765)
              │ runs/api.py + runs/execute.py
              ▼
LCA Agent/Team 运行时 (layer2~3)
              │ record() → jsonl + LiveTail
```

默认聊天模型 `solo`。两条路不相交：
- `POST /runs` + `GET /runs/{id}/live`：Agent 干活
- `POST /v1/chat/completions` / embeddings / responses：标题与系统小助手（`openai_shim`）

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
| `gateway/openai_shim.py` | OpenAI 兼容 HTTP 面（标题 / embeddings / responses） |


升级：`LOBEHUB_RELEASE=v2.2.14 ./scripts/sync_lobehub_ui.sh`
