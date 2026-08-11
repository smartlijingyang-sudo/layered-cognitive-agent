# LobeHub UI 集成

> 分支：`feat/lobehub-ui-integration`  
> 目标：用 LobeHub 官方 UI 替换自研 `web/`，LCA Python 后端提供 OpenAI 兼容面。

## 版本策略

| 项 | 值 |
|---|---|
| 使用版本 | **v2.2.13**（官方最新 stable release） |
| 来源 | `https://github.com/lobehub/lobehub.git`（仅此，无外部 fork） |
| 运行副本 | `lobehub-ui/`（gitignore，LCA 项目内独立一份） |
| git 缓存 | `.lobehub-upstream/`（gitignore，仅用于 sync 脚本） |

**完全自包含**：不读取、不依赖、不 rsync 本机任何其他 lobehub 目录。
所有路径相对 LCA 仓库根目录，见 `deploy/lobehub/README.md`。

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

v2.2.13 通过标准 **OpenAI provider** 对接 LCA gateway；默认聊天模型为 **`solo`**（LCA 后端，内部使用根目录 `.env` 的 `LLM_MODEL` / 百炼 Qwen）：

```env
OPENAI_API_KEY=lca-local
OPENAI_PROXY_URL=http://127.0.0.1:8765/v1
ENABLED_OPENAI=1
DEFAULT_AGENT_CONFIG=model=solo;provider=openai;chatConfig.searchMode=off
QWEN_PROXY_URL=http://127.0.0.1:8765/v1
QWEN_API_KEY=lca-local
```

**全部走 LCA gateway**（2026-08 补丁）：
- 主聊天 + 系统 mini agent：`openai` / `solo` → `POST /v1/chat/completions` → LCA run
- `solo`/`team` 模型强制走 chat/completions（不因联网搜索切到 Responses API）
- `POST /v1/embeddings`：gateway 代理上游 embedding
- `POST /v1/responses`：json_schema 结构化输出走上游；普通 chat 回落 LCA run
- Qwen provider 也指向 gateway（不再直连 DashScope）

联网搜索由 LCA 后端统一搜索平面控制（ADR-0053）：

| 路径 | 条件 |
|------|------|
| `web_search` → `lobe-web-browsing____search` | `TAVILY_API_KEY` 已配置 |
| Qwen `enable_search` 兜底 | `LLM_ENABLE_SEARCH=true`，或 Tavily 失败 / 无 key |

不再依赖 LobeHub 直连 DashScope 的 `enable_search`，也不应在沙箱内安装 `tvly` CLI。

## 快速开始

```bash
chmod +x scripts/sync_lobehub_ui.sh scripts/start_lobehub_stack.sh

# 1. 从官方拉取 v2.2.13 到 lobehub-ui/
./scripts/sync_lobehub_ui.sh

# 2. （可选）启动 postgres/redis/rustfs
cd lobehub-ui/docker-compose/dev && cp .env.example .env && docker compose up -d

# 3. 联合启动 gateway + LobeHub dev
./scripts/start_lobehub_stack.sh dev
```

环境模板：`deploy/lobehub/.env.lca` → 自动复制为 `lobehub-ui/.env`

## 后端适配进度

| 端点 | 状态 |
|---|---|
| `GET /v1/models` | ✅ 返回 LCA modes（solo, team） |
| `POST /v1/chat/completions` | ✅ journal→OpenAI SSE 桥接（solo / team → LCA run） |
| Tool UI 对齐 | ✅ LCA tool → `lobe-skills____*` + `lobe-cloud-sandbox____*` + `lobe-web-browsing____search` wire |
| Mode A 闭环 | ✅ 工具生命周期仅 `lca.events`（`tool_started`/`tool_result`/`tool_state`）；不发 `delta.tool_calls`；LobeHub 跳过 client tool loop |
| Unified Search | ✅ Tavily REST + Qwen native fallback (ADR-0053) |
| Computer Use | ✅ 13 个 cloud-sandbox 工具 + `terminalExec`（Onlyboxes） |
| 内容边界 | ✅ `ResponseTextStreamExtractor` — Decision JSON 不进 `delta.content`，仅 `response_text` 流式 |
| LobeHub XML 净化 | ✅ 剥离 `<available_tools>` / `<agent_management_context>` 再进 LCA prompt |
| 本地无登录模式 | ✅ `ENABLE_MOCK_DEV_USER` → LocalDevAuth（无 get-session 轮询）+ API mock user |
| 话题页路由稳定 | ✅ pathname 兜底解析 topicId，避免 session/重渲染误跳转 |
| `POST /v1/responses` | ✅ json_schema 结构化输出；普通 chat 回落 LCA run |
| `POST /v1/embeddings` | ✅ 代理上游 embedding API |
| 系统 mini agent 默认模型 | ✅ 补丁为 Qwen 直连（避免 gpt-5.x 走 `/v1/responses` 404） |
| 原有 `/runs` SSE API | ✅ 保留，供 legacy `web/` 使用 |

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

## 升级 release

```bash
LOBEHUB_RELEASE=v2.2.14 ./scripts/sync_lobehub_ui.sh   # 未来版本
```
