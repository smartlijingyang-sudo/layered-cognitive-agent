# ADR-0202 — Transport/UI env 配置 SSOT

## 状态

**Proposed** (2026-09-08). Refs: AGENTS.md §4 env 三层白名单, ADR-0171 (process lifecycle env), the recent lobehub deploy fix batch (8+ fixes since 2026-08-30).

## 0. 决策摘要

Transport 与 LobeHub 部署栈(`.env.lca` ↔ bun 子进程 env ↔ SPA bundle 注入 ↔ WS URL / JWT secret)经五处独立 read path 拼装,无 SSOT,导致 2026-08-30 以来同一根因的 8+ 个 `fix(lobehub)` 提交。本 ADR 把 env 消费收口到 Profile `{from_env: ...}` seam;plugin / patch / webserver handler **不得**直读 `os.environ` 或 `process.env`;新增 `lca.infrastructure.profile.env_resolve()` 在 boot 一次性 resolve,运行时读取即 bug。Legacy fallback 路径进入退役倒计时。

## 1. 第一性原理

| ID | 原理 | 落地 |
|---|---|---|
| SSOT 唯一 | env 值只有一处真值;`.env` / Profile yaml / 运行时 env 三层只在 boot 端合并 | `lca_kernel.env.load_layered_env` + `Profile.expand_env_refs` |
| 3.3 控制/观察分离 | env 是控制面配置;boot 期一次性 ingest,运行期 mutation 即副作用 | `env_resolve()` 返回 frozen `EnvSnapshot`;plugin 只读不写 |
| C8 确定性 | Profile resolve / fold / projection 必须确定;env 经 seam 注入 | boot 集中 resolve,运行期零 `os.environ.get` |
| AGENTS §4 普适 | 插件不得自行读取 `os.environ`(不变量 P3) | 不只 webserver,lobehub patch / host console / middleware 全纳入 |
| ADR-0117 K7 兼容 | `BOOTSTRAP_NAMES` / `_PREFIXES` / `_FORBIDDEN` 是 boot 端白名单 | Profile `{from_env}` 是运行期白名单,两者正交不冲突 |

## 2. 受影响的契约与代码

### 2.1 Profile `{from_env: ...}` 现有用法

`lca/harness/profile/plan/declarations.py:expand_env_refs` 声明形:

```yaml
config:
  assistants_root:
    from_env: LCA_ASSISTANTS_ROOT
    required: false
```

当前 bundle 仅 **2 处声明**(`bundles/assistant-runtime.yaml:9` `LCA_ASSISTANTS_ROOT`, line 32 `LCA_LOBEHUB_URL`)。

### 2.2 audit:`deploy/lobehub/` Python 直读

`grep -rn "os\.environ\|os\.getenv" deploy/lobehub/ --include='*.py'` → **0 处**。

### 2.3 audit:`lca/plugins/transport/webserver/` 直读

| path:line | 引用 | 状态 |
|---|---|---|
| `handlers/runs/terminal/streaming/auth.py:17` | `import os` | legacy fallback |
| `handlers/runs/terminal/streaming/auth.py:61` | `os.environ.get(name)` → `LCA_JWT_SECRET` / `LCA_JWT_PUBLIC_KEY` | legacy,带 `DeprecationWarning` |
| `handlers/runs/terminal/streaming/auth.py:64` | warning 文本 | 同上 |

`jwt_keys_seam/jwt_keys.py` 自身零 env 直读;`bundles/web-app.yaml` 当前 `dev_mode: true` 永不触发 fallback,但代码仍在 = 债务。

### 2.4 audit:`deploy/lobehub/patches/*.{ts,tsx}` 的 `process.env.*`

`grep -rc "process\.env" deploy/lobehub/patches/ --include='*.ts' --include='*.tsx'` → **38 次**,11 个 patch 模块: `proxy/file_proxy_rewrite.py:7`、`runtime/lca_runtime_agent_gateway.py:6`、`devux/lan_dev.py:10`、`runtime/lcaGateway/client.ts:3`、`runtime/LcaComposioApi.ts:4`、`auth/dev_auth_files.py:3`、`auth/middleware_mock_user.py:1`、`ui/LcaHostConsole.tsx:1`、`runtime/lcaRunCommand.ts:1`、`runtime/lcaRunObserve.ts:1`、`runtime/lcaGateway/executeGatewayRun.ts:1`。消费 env:`LCA_GATEWAY_PUBLIC_URL`、`NEXT_PUBLIC_LCA_TOKEN` / `_GATEWAY_URL` / `_COMPOSIO_URL` / `_ENABLE_MOCK_DEV_USER` / `_MOCK_DEV_USER_ID` / `_LCA_HOST_CONSOLE` / `_OPENAI_PROXY_URL`、`VITE_DEV_HOST` / `_PORT`、`ENABLE_MOCK_DEV_USER`、`MOCK_DEV_USER_ID`、`OPENAI_PROXY_URL`。

### 2.5 audit:`deploy/lobehub/.env.lca` env 名

`grep -E "^[A-Z_][A-Z0-9_]*=" deploy/lobehub/.env.lca | sed 's/=.*//' | sort -u` → **51 个** 唯一 env 名。

**49 个未在任何 bundle 的 `from_env:` 声明**,含:

- `LCA_GATEWAY_PUBLIC_URL` —— SPA bundle + bun 子进程都消费,但无 bundle 注入;8+ fix 的核心。
- `LCA_JWT_SECRET` / `LCA_JWT_PUBLIC_KEY` —— jwt_keys_seam 显式依赖 `from_env`,但 `bundles/web-app.yaml` 当前 `dev_mode: true`;切换生产 bundle 即 crash。
- `NEXT_PUBLIC_LCA_*` / `LCA_HOST_*` / `LCA_LOBEHUB_INGEST_*` —— 同病。

## 3. Profile seam contract

### 3.1 声明形

```yaml
config:
  jwt:
    private_pem: {from_env: LCA_JWT_SECRET, required: true}
    public_pem:  {from_env: LCA_JWT_PUBLIC_KEY, required: true}
    dev_mode: false
  gateway:
    public_url: {from_env: LCA_GATEWAY_PUBLIC_URL, required: true}
```

### 3.2 运行时 resolve

新增 `lca/infrastructure/profile/env_resolve.py`:

```python
def env_resolve(
    declared: Mapping[str, EnvRef],
    *,
    env: Mapping[str, str] | None = None,
) -> EnvSnapshot:
    """Resolve Profile-declared env refs in a single boot-time call.

    Returns frozen EnvSnapshot; downstream reads via snapshot.get(name)
    / snapshot.secret(name) and never calls os.environ again. Harness
    calls once during compile_profile(); result feeds app.state.env
    (transport) and ctx.inject('env') (plugins).
    """
```

要点:输入 = `{field_path: from_env_name}` + 当前 `EnvSnapshot`(BOOTSTRAP_NAMES 子集);输出 frozen;`secret()` 返回 `SecretStr`;缺 key 且 `required: true` → fail-loud at boot。

### 3.3 bootstrap invariant

| 时机 | 允许 |
|---|---|
| boot (`compile_profile` / `load_layered_env` / `expand_env_refs`) | 读 `os.environ` + `.env` + 解析 `{from_env}` |
| resolve 后 | 注入 `app.state.env` + `ctx.inject('env')` |
| 运行期 (handler / plugin setup / patch apply) | **只** 经 `EnvSnapshot` / `ctx.inject('env')` 读 |
| 运行期任何 `os.environ.get(...)` 或 `process.env.NAME` | bug;架构测试 fail |

SPA 的 `process.env.NEXT_PUBLIC_*` 由 bun 子进程 spawn 时 set —— 等同"运行期直读"。补救:bun 启动前由 LCA CLI 调 `env_resolve()` 把值注入 spawn env,而非 SPA 自己 `process.env` 兜底。

## 4. delete-when

```bash
# (a) Python 直读
grep -rn "os\.environ\|os\.getenv" deploy/lobehub/ lca/plugins/transport/webserver/

# (b) Python patch import os
grep -rnE "^import os$|^from os import " deploy/lobehub/patches/

# (c) bundle 覆盖度
comm -23 \
  <(grep -E "^[A-Z_][A-Z0-9_]*=" deploy/lobehub/.env.lca | sed 's/=.*//' | sort -u) \
  <(grep -rh "from_env:" bundles/ | awk '{print $2}' | sort -u)
# → 0 行
```

分阶段:

| 阶段 | 条件 |
|---|---|
| PR-1 | 架构测试通过(`auth.py` legacy 在 exception list) |
| PR-2..N | 每 commit (a) `_env_fallback` 计数 -1;(b) 至少 1 个新 `from_env:`;(c) 关联 patch 不依赖裸 `process.env` |
| 最终 | 全部 grep = 0;`auth.py` 删除 `_env_fallback`;legacy 行数 = 0 |

## 5. 验证

`tests/architecture/test_0202_env_ssot.py`(要点): import `lca.infrastructure.profile.env_resolve.env_resolve + EnvSnapshot` 必须可 import;扫描 `lca/plugins/transport/webserver/` + `deploy/lobehub/patches/` 下 `*.py` 中 `os\.environ|os\.getenv`(`auth.py` 在 ALLOWED_EXCEPTIONS 内,中期);扫描 `bundles/*.yaml` 中 `from_env:` 集合与 `deploy/lobehub/.env.lca` 顶层 key 名集合差集必须为空。三个 assertion 全过 = ADR §4 全绿。

## 6. 迁移计划

| PR | 内容 | delete-when |
|---|---|---|
| PR-1 | 本 ADR 接受 + `env_resolve()` 实现 + 架构测试(允许 `auth.py` legacy exception) | 测试通过 |
| PR-2 | `bundles/web-app.yaml` 加 `jwt.{private,public}_pem.from_env`;`auth.py` 打 deprecation warn | `_env_fallback_warned` 计数 ≥ 1 |
| PR-3 | `bundles/web-app.yaml` 加 `gateway.{public_url,ws_url,token}.from_env`;LCA CLI 在 bun spawn 前调 `env_resolve()` 注入 | `lca-ops status --json child_env_lca.json` 列全注入变量 |
| PR-4 | `patches/proxy/file_proxy_rewrite.py` 把 `process.env.LCA_GATEWAY_PUBLIC_URL` 改 window-injected | `grep "process.env.LCA_GATEWAY_PUBLIC_URL" deploy/lobehub/patches/` = 0 |
| PR-5..N | 逐 patch 把 `NEXT_PUBLIC_LCA_*` / `VITE_*` / `ENABLE_MOCK_*` 改 build-time inject 或 window global | `grep -rE "process\.env\.(NEXT_PUBLIC_LCA_\|NEXT_PUBLIC_OPENAI_\|VITE_\|ENABLE_MOCK\|NEXT_PUBLIC_ENABLE_MOCK)" deploy/lobehub/patches/` = 0 |
| 最终 | 删 `auth.py._env_fallback` + 删 `ALLOWED_EXCEPTIONS` + strict 测试 | `test_0202_env_ssot.py` exit 0 且所有 grep = 0 |

## 7. 关联

- AGENTS §4(密钥只能经 `{from_env: ...}`;plugin 不得直读 `os.environ`)。
- ADR-0061 §决定 5(`{from_env}` → `SecretStr`,harness 端单轨)。
- ADR-0117 K7(boot 端白名单;本 ADR 是运行期白名单,正交不冲突)。
- ADR-0122 §验证(`rg 'os\.environ' lca/plugins/assistant` → 0 必要条件;本 ADR 扩展到 transport + deploy)。
- ADR-0171 `expand_env_refs` 实现位置。
- ADR-0187 §3 D6(首个跨 lobehub+webserver env seam 范本)。
- 实施 note:`docs/notes/implemented/seam/2026-09-08-transport-ui-env-ssot.md`。
