# Agent Note: Transport/UI env SSOT audit — ADR-0202 落地盘点

Status: implemented

## Problem

2026-08-30 以来 8+ 个 `fix(lobehub)` 提交共用同一根因:env 在 `.env.lca` ↔ bun 子进程 env ↔ SPA bundle 注入 ↔ WS URL / JWT secret 五处 read path 各自独立,无 SSOT。AGENTS §4 已有 standing rule 但未被审计,transport + deploy 栈内多站违规。

## Decision

按 ADR-0202 收口。`env_resolve()` 新增于 `lca/infrastructure/profile/env_resolve.py`,boot 一次性 resolve,运行期只读 `EnvSnapshot`。架构测试 `tests/architecture/test_0202_env_ssot.py` 守护三条 invariant: (a) plugin / patch Python 直读 `os.environ` = 0; (b) bundle `from_env:` 覆盖 `.env.lca` 全 key; (c) `env_resolve` 可 import。

## Audit findings

### A. `deploy/lobehub/` Python 直读 `os.environ` / `os.getenv`

**0 sites**。`grep -rn "os\.environ\|os\.getenv" deploy/lobehub/ --include='*.py'` 空。Python 端干净,违反全部发生在 TS 插入字符串(见 B)。

### B. `deploy/lobehub/patches/*.{ts,tsx}` 的 `process.env.*` = **38 sites / 11 files**

| patch | 引用次数 |
|---|---|
| `proxy/file_proxy_rewrite.py` | 7 |
| `runtime/lca_runtime_agent_gateway.py` | 6 |
| `devux/lan_dev.py` | 10 |
| `runtime/lcaGateway/client.ts` | 3 |
| `runtime/LcaComposioApi.ts` | 4 |
| `auth/dev_auth_files.py` | 3 |
| `auth/middleware_mock_user.py` | 1 |
| `ui/LcaHostConsole.tsx` | 1 |
| `runtime/lcaRunCommand.ts` | 1 |
| `runtime/lcaRunObserve.ts` | 1 |
| `runtime/lcaGateway/executeGatewayRun.ts` | 1 |

### C. `lca/plugins/transport/webserver/` 直读 `os.environ` / `os.getenv` = **3 sites / 1 file**

全部在 `handlers/runs/terminal/streaming/auth.py`(legacy fallback):
- line 17 `import os`
- line 61 `os.environ.get(name)` → `LCA_JWT_SECRET` / `LCA_JWT_PUBLIC_KEY`
- line 64 DeprecationWarning message

`jwt_keys_seam/jwt_keys.py` 自身零直读(8–17 行为 docstring 引用)。CLI `serve.py:_preflight_jwt_secret` 读 `os.environ` 不在禁列(CLI 而非 plugin)。

### D. `.env.lca` env 名 = **51 唯一**;bundle `from_env:` 声明 = **2 唯一** → 49 未声明

只声明:`bundles/assistant-runtime.yaml:9` `LCA_ASSISTANTS_ROOT`, line 32 `LCA_LOBEHUB_URL`。

未声明关键:`LCA_GATEWAY_PUBLIC_URL`、`LCA_JWT_SECRET` / `LCA_JWT_PUBLIC_KEY`、`NEXT_PUBLIC_LCA_TOKEN` / `_GATEWAY_URL` / `_COMPOSIO_URL` / `_OPENAI_PROXY_URL` / `_ENABLE_MOCK_DEV_USER` / `_MOCK_DEV_USER_ID` / `_LCA_HOST_CONSOLE`、`VITE_DEV_HOST` / `_PORT`、`LCA_HOST_TOKEN` / `_DEVICE_ID` / `_USER`、`LCA_LOBEHUB_INGEST_*`、`KEY_VAULTS_SECRET`、`ONLYBOXES_*`、`QSTASH_*`、`REDIS_*`、`S3_*`、`RUSTFS_*`、`DATABASE_*`、`QWEN_*`、`OPENAI_*`。

## Verification

- `tests/architecture/test_0202_env_ssot.py`: (a) `_scan_os_env_reads()` 扫 `(lca/plugins/transport/webserver, deploy/lobehub/patches)`,`auth.py` 在 `ALLOWED_EXCEPTIONS` 中期; (b) `_test_all_env_lca_vars_declared` 计算 `.env.lca` 实际 key 集与 `bundles/*.yaml` 中 `from_env:` 名集差集 = 空; (c) `from lca.infrastructure.profile.env_resolve import env_resolve, EnvSnapshot` 不抛 `ImportError`。
- `grep -rn "os\.environ" deploy/lobehub/ lca/plugins/transport/webserver/` 在 PR-N 中逐次收敛至 0。
- `comm -23` 测试在 PR-3 (gateway env) + PR-N (lobehost / ingest) 后逐步收敛。

## Consequences

- `bundles/web-app.yaml` 必须新增 `jwt.*.from_env` + `gateway.*.from_env` 字段;生产 bundle 不能默认 `dev_mode: true`。
- SPA `process.env.NEXT_PUBLIC_*` 改为 bun spawn 时 `--define` 注入或 window global;lca-ops CLI 在 spawn 前调 `env_resolve()`。
- `auth.py._env_fallback` 在最终态删除;当前带 `DeprecationWarning` 中间态,prod 触发计数是 delete-when 信号。

## Related

- ADR-0202(本 ADR)。
- ADR-0061 §5(`expand_env_refs`)。
- ADR-0117 K7 / ADR-0122 §验证 / ADR-0171 / ADR-0187 §3 D6。
- `docs/notes/implemented/seam/2026-09-07-jwt-secret-injection-via-profile.md`(同方向的前置 note)。
