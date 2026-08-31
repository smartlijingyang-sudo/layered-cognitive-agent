# ADR-0119 Followup-2: 全 6 类 "gateway" 命名清理

**状态:** Accepted
**日期:** 2026-08-31
**父 ADR:** [0119-followup-gateway-name-map.md](0119-followup-gateway-name-map.md)
**关联 ADR:** [0119-webserver-as-plugin.md](0119-webserver-as-plugin.md) ·
[0112-gateway-routes-as-plugins.md](0112-gateway-routes-as-plugins.md) ·
[0115-kernel-transport-boundary.md](0115-kernel-transport-boundary.md) ·
[0117-process-lifecycle-env-whitelist.md](0117-process-lifecycle-env-whitelist.md) ·
[0076-six-plane-capability-layout-and-substitution-test.md](0076-six-plane-capability-layout-and-substitution-test.md) ·
[0106-naming-constitution.md](0106-naming-constitution.md)

## 背景

ADR-0119 followup 已经把 "gateway" 命名按 6 类分类,并决定 A 类(进程层)改 `KernelServe*`、B/C/D/E/F 类保留。本 ADR 把范围扩到全部 6 类 — 即把 ADR-0119 followup 中保留的 5 类也一并替换为符合语境的名词。

触发条件:
1. 用户要求"将 gateway 名字从项目彻底清理,换成符合语境的名词"。
2. 同期 `deploy/dsh/` 与顶层 `gateway/` 目录已经被 retire,意味着 D 类保留路径(`gateway/plugins/default_modes.py`)**已经不可能物理保留**;原 commit 的"保留 namespace"语义被本批 PR 推翻。
3. C 类 `CommandGateway` 命名与命名宪法 §4.1("角色后缀必须是 30 个之一")冲突:`Gateway` 不是 §4.1 任何后缀。
4. B 类 `GatewayRouter` 同上。
5. E 类 emitter 是 wire schema 字段,但只在 journal v2 envelope 里写盘,可以加 aliases 兼容老文件。
6. ADR-0076 的 `EffectGateway` / `RuntimeEffectGateway` / `RegistryEffectGateway` 抽象层命名同样违反命名宪法 §4.1。

## 决定

### 改名映射(全 6 类 + Effect 抽象 + device 子目录)

| 现名 | 新名 | 类 | 备注 |
|---|---|---|---|
| `OpsConfig.gateway` (Pydantic 字段) | `OpsConfig.kernel_serve_network` | A | SSOT 同步 `lca-ops.yaml` |
| `GatewayConfig` (类) | `KernelServeNetworkConfig` | A | 类名直陈 |
| `GATEWAY_HOST/PORT/BIND` (env) | `LCA_KERNEL_SERVE_HOST/PORT/BIND` | A | 新 prefix,旧 env 兼容期 |
| `BOOTSTRAP_PREFIXES` 的 `"GATEWAY_"` | 加 `"LCA_KERNEL_SERVE_"`,保留 `"GATEWAY_"` 兼容 | A | env 白名单 |
| `_GATEWAY_REFUSAL_CODES` (常量) | `_KERNEL_SERVE_REFUSAL_CODES` | A | CLI journal 注释同步 |
| `LcaGatewayRouter` (Protocol) | `RouteRegistryProtocol` | B | 命名宪法 §4.1 |
| `GatewayRouter` (类) | `RouteRegistry` | B | 同上 |
| `gateway_router` (capability key) | `route_registry` | B | plugin boot shim 兼容 |
| `GatewayBootstrap` / `GatewayBootstrapConfig` / `GatewayBootstrapFactory` / `DefaultGatewayBootstrapFactory` | `WebserverBootstrap` / `WebserverBootstrapConfig` / `WebserverBootstrapFactory` / `DefaultWebserverBootstrapFactory` | B | "webserver" 是 ADR-0106 §4.1 限定命名空间 |
| `gateway_bootstrap_factory` / `gateway_bootstrap_config` (capability keys) | `webserver_bootstrap_factory` / `webserver_bootstrap_config` | B | 同上 |
| `gateway_bootstrap.installed` (event) | `webserver_bootstrap.installed` | B | event catalog 同步 |
| `service.register("gateway_bootstrap", ...)` (boot 注册) | `service.register("webserver_bootstrap", ...)` | B | 同步 |
| `CommandGateway` (类) | `SessionCommandDispatcher` | C | 命名宪法 §4.1 "Dispatcher" 后缀 |
| `lca/harness/command/gateway.py` (module) | `lca/harness/command/dispatcher.py` | C | 文件↔类一一对应 |
| `emitter="lca.harness.command.gateway"` (wire field) | `emitter="lca.harness.command.dispatcher"` | E | reader aliases 兼容老 journal |
| `lca.harness.command.gateway` (Python module path,被 4 处 import) | `lca.harness.command.dispatcher` | C+E | import shim 模块留 1 release |
| `gateway/plugins/default_modes.py` (module path) | 物理已删除,emitter 改为 `lca.cognition.team.modes.default_modes` | D | retire dsh 后目录已无,emitter 跟着改 |
| `emitter="gateway.plugins.default_modes"` (wire field) | `emitter="lca.cognition.team.modes.default_modes"` | D | reader aliases 兼容老 journal |
| `EffectGateway` (Protocol) | `EffectDispatcher` | Effect | 命名宪法 §4.1 |
| `EffectGatewayFactory` (Protocol) | `EffectDispatcherFactory` | Effect | 同上 |
| `EFFECT_GATEWAY_FACTORY` (Capability key 常量) | `EFFECT_DISPATCHER_FACTORY` | Effect | 同步 |
| `effect_gateway_factory` (capability key 字符串) | `effect_dispatcher_factory` | Effect | plugin boot shim 兼容 |
| `RegistryEffectGateway` (类) | `RegistryEffectDispatcher` | Effect | 同步 |
| `receipt_from_gateway` (函数) | `receipt_from_dispatcher` | Effect | 函数直陈职责 |
| `lca/infrastructure/device_gateway/` (目录) | `lca/infrastructure/device_hub/` | Device | "hub" 是 ADR-0106 §4.1 后缀 |
| `lca/plugins/transport/device_gateway/` (目录) | `lca/plugins/transport/device_hub/` | Device | 同上 |
| `DeviceGatewaySettings` (类) | `DeviceHubSettings` | Device | 类名直陈 |
| `pyproject.toml` `[tool.lca.package_contracts.gateway.*]` | `[tool.lca.package_contracts.webserver.*]` 与 `[tool.lca.package_contracts.device_hub.*]` | F | package 边界同步 |
| 53 个 `lca/*/README.md` 第 25 行 `^- \`gateway\`$` | 实际指向被改 module path 的 README 才更新;其余保留字面 | F | README 模板 forbidden_deps 同步 |
| 87 个 docs/ 历史叙述中 `gateway` 字面 | 不动字面 | F | 历史叙述保留,新文件不再用 |

### wire schema / capability key / env / module 兼容期

全部使用 **新名字 + 旧名字 shim** 模式,有效期到 **2026-12-31**(commit 后约 4 个月)。

1. **capability key shim**: 在 `lca/plugins/transport/webserver/router.py` 与 `lca/plugins/providers/journal/declarative_runtime_seams.py` 等 provider plugin 的 `setup()` 第一行读 ctx:若 ctx 已 provide 旧 key 但未 provide 新 key,自动 provide 新 key。plugin tree 启动顺序不变。
2. **env var shim**: `cli/config.py._apply_environ` 优先读 `LCA_KERNEL_SERVE_*`,旧 `GATEWAY_*` 走 path 触发 structlog deprecation warning(`event="env_var_deprecated"`,`old="GATEWAY_HOST"`,`new="LCA_KERNEL_SERVE_HOST"`)。
3. **emitter shim**: `event_descriptors_data.py` 维护 `_EMITTER_ALIASES` dict,reader 解析时 `resolved = _EMITTER_ALIASES.get(raw, raw)`,老 JSONL 文件仍可读。
4. **module path shim**: `lca/harness/command/gateway.py` 留 1 release 的 import-compat shim,内容只 re-export `lca.harness.command.dispatcher` 公共符号,带 deprecation module docstring。

### 不在范围(scope creep 防护)

| 项 | 原因 |
|---|---|
| `packages/gateway-client/` (npm SDK 包名) | 外部 SDK,改 npm 包名要协调发布 |
| `deploy/lobehub/patches/*` 内 JS/TSX 代码 | LobeHub UI patch,非 LCA 代码,JS 标识符不在 ADR 范围 |
| `LCA_GATEWAY_PUBLIC_URL` (LobeHub patch 引用的 env var) | 同上,外部集成契约 |
| `CHANGELOG.md` 历史段落 | 已写过的版本不动 |
| `vendor/` | vendor 改动必须有升级/修复理由 |
| `tests/test_architecture_gateway.py` 文件名 | **改名**为 `tests/test_architecture_naming.py`(本批 PR 顺手) |
| 87 个 docs/ 历史叙述 | ADR-0119-followup F 类延续 |

## 后果

正面:
- gateway 命名在 LCA 内部彻底消除,新代码读者不会再把它和 ADR-0119 决定的 kernel_serve 进程混淆。
- 命名宪法 §4.1 在 contracts / plugins / harness 层全面合规(`Router` / `Dispatcher` / `Registry` / `Factory` / `Settings` 都是 §4.1 后缀)。
- capability key 与命名空间同步收紧,plugin tree 启动顺序与契约不变。

负面:
- 100+ Python 文件改 import / capability key / 类名 / 函数名;wire schema 双写期;module path 1 release 兼容期。
- 需要更新 ADR-0119-followup,顶部加 "Superseded by followup-2 for B/C/D/E/F classes; A class unchanged"。

## 索引

- ADR-0119 followup 上一版:`docs/adr/0119-followup-gateway-name-map.md`
- 落地:`lca/contracts/protocols/route_registry.py` (新) + `lca/plugins/transport/webserver/router.py` + `lca/harness/command/dispatcher.py` (新)
- 落地:`lca/infrastructure/device_hub/` (新) + `lca/plugins/transport/device_hub/` (新)
- 落地:`lca/infrastructure/cli/config.py:KernelServeNetworkConfig` + `lca/infrastructure/env/bootstrap.py:LCA_KERNEL_SERVE_`
- 落地:`lca/infrastructure/observability/events/event_descriptors_data.py:_EMITTER_ALIASES`
- 落地:`pyproject.toml` `[tool.lca.package_contracts.webserver]` + `[tool.lca.package_contracts.device_hub]`