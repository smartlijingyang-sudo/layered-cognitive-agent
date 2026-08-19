# Cordis 迁移 — 把 LCA 插件系统换成 Taiyi Cordis

**日期**: 2026-08-19
**状态**: Draft（brainstorm 通过；待 spec-reviewer 评审）
**关联**:
- [2026-08-16-plugin-tree-runtime-design.md](./2026-08-16-plugin-tree-runtime-design.md)（已经把 21 个 capability 插件拆出来；本设计是它的运行时承接）
- [2026-08-14-deepseek-harness-integration-analysis.md](./2026-08-14-deepseek-harness-integration-analysis.md)（"借鉴不搬"已经在做）
- ~/taiyi-agent（DSH 的 Python 移植，旁路对照）+ ~/deepseek-harness（DSH 原文，旁路对照）
- ADR-0004 Protocol-First、ADR-0005 L4 组合根、ADR-0037 Journal-as-Truth

---

## 0. 一句话

LCA 现有 21 个 capability 插件都还跑在自家 `lca/layer0_infra/plugin/` 这个 in-house kernel 上，它只是 cordis 风格的**简化复刻**。本设计把整个 in-house kernel 删掉，**vendor 引入 `~/taiyi-agent/vendor/cordis`**（DSH cordis 的 1:1 Python 移植），把 21 个插件改写为 cordis 的 `@plugin` 形式，把 bundle / profile / composer 全部接到 cordis 的 loader + context 上。

不立 dsh 100+ 包的 port flag——cordis 是唯一 vendor 依赖，能力自建。

---

## 1. 范围 / 非目标

**In**:
- 替换 `lca/layer0_infra/plugin/` 为 cordis
- 替换 `lca.harness.kernel`（ScopedPluginHost / compat）为 cordis
- 替换 `lca.harness.profile/boot.py` 为 cordis.Loader 的薄包装
- 删 `lca/contracts/harness/plugin.py`（保留 `MiddlewareRegistration` 等在 `middleware.py`）— 实际是拆 `plugin.py`：删 `Manifest`/`ExtensionPoint`/`CapabilityGrant`/`ScopeKind`/`PluginKind`/`ProviderMode`，保留 `PluginContext` Protocol
- 删 `lca/contracts/mechanisms/seam.py` 中的 `SeamRole`/`SeamDeclaration`/`SeamRegistry`/`seam`/`validate_all_seams`；**保留 `consume()`**（composition-time gate，3 个 production 文件 + tests 依赖）
- 删 `lca/contracts/mechanisms/plugin.py` 中的 `Plugin` Protocol；**保留 `PluginConfig`**（Pydantic 基类，多个 plugin 和 test 依赖）
- 21 个 `lca/plugins/*` 改写为 `@plugin` 形式
- `bundles/base-spine.yaml` + `profiles/web-standard.yaml` 改为 cordis YAML（用 `id` 不是 `name`）
- `lca/layer4_app/composer.py:_isolate_agent_scope` 用 cordis Context 改写（`Context.scope(label)` 不是 `Context.isolate(label)`）
- vendor 引入 `taiyi-cordis` / `taiyi-cosmokit` / `taiyi-schemastery`

**实际 service 文件状态**：
- `LlmService` **保持不继承 `cordis.Service`**——它是 `LLMAdapter` 实现，不会随 ctx dispose 消失。Plugin 提供 `LlmService()` 实例并 `ctx.provide("llm", ...)`，由 Service Definition 自身管理生命周期。
- `cordis.Service` 用在真需要 auto-dispose 的组件上（HTTP 客户端、DB 连接）。LCA 当前的 Service Definition 类都不是这种。

**Out**:
- 不 port dsh 100+ 包（subagent / sandbox / LSP / MCP / ACP / compaction / skill / goal / workflow / jobs / todo / plan / preset / guard / hooks / session-query / settings / credentials / attachment / fs / lsp / terminal / code-runtime / shell / subprocess / e2b / feedback / context / identity / interaction / web / storage / workspace / boot / sdk / examples / support / util / typert）
- 不重写 `lca/contracts/protocols/` 的 16 个 Protocol
- 不动 LCA 5 层单向依赖 import 图
- 不动 `lca/contracts/{atoms,models}/` 纯数据契约
- 不改 Journal 真相机制（ADR-0037）
- 不改 L4 组合根 API（`Agent` / `Team` / `TeamLead`）

---

## 2. 第一性原理

1. **vendor 唯一 = cordis**。DSH 的 cordis 是经过产品考验的运行时；taiyi 的 1:1 Python 移植可用。LCA 自家复刻只是临时脚手架，留下来就是双轨约定。
2. **协议是架构的硬骨；runtime 是方法的肉**。`lca/contracts/protocols/` 的 16 个 `@runtime_checkable Protocol` 是真抽象，价值高于 runtime——保留。`lca/contracts/harness/plugin.py` 的 `Manifest`/`ExtensionPoint`/`CapabilityGrant` 在 dsh 都没对应物，是 LCA 早期自创的中间层，删。
3. **plugin = 行为单位**。21 个 capability 插件都是有用的；plugin 集不缩——只在文件夹 + 命名上重新组织。
4. **scope 在 cordis 上重新表达**。LCA 自创的 5-ScopeKind 是语义名词（DEPLOYMENT/PROFILE/TEAM/AGENT/SESSION），cordis 的 `Context.scope(label)` / `Context.fork()` 不需要语义枚举——`"agent:{role}"` 这种 label 字符串足够。把 ScopedPluginHost 从一个类简化成一个 `async with ctx.scope(label)`。
5. **bundles 是装配面，不是行为面**。bundle 文件只是 entry 列表 + 顺序；行为住在 setup callback 里。`seam_definitions` 这种"纯声明"插件是 cordis 不需要的——`@plugin(name="...")` 自己声明。
6. **L4 仍是组合根**。Composer（`lca/layer4_app/composer.py`）知道整棵树；其他层只挂自己那一层的插件。

---

## 3. 架构总图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 当前（要删）                                      →  目标（cordis）         │
├─────────────────────────────────────────────────────────────────────────────┤
│ lca/layer0_infra/plugin/{kernel,loader,include,   delete                    │
│   scope,expr,builtins}                                                       │
│ lca/harness/kernel/{scope,compat}                  delete                    │
│ lca/harness/profile/boot.py                        delete (rewrite)         │
│ lca/contracts/harness/plugin.py                    delete                    │
│ lca/contracts/mechanisms/plugin.py                 delete                    │
│ lca/contracts/mechanisms/seam.py                   delete                    │
│                                                                              │
│ vendor/cordis (empty)                               vendor  ← taiyi/src      │
│ vendor/cosmokit (empty)                             vendor  ← taiyi/src      │
│ vendor/schemastery (empty)                          vendor  ← taiyi/src      │
│                                                                              │
│ lca/plugins/*/  (21 manifest-form)                  rewrite → @plugin-form  │
│   ├ 17 保留原位                                                            │
│   ├ 2 改名 policy → guard                                                │
│   ├ 1 合并 agent_service → session_service                                │
│   └ 1 删 seam_definitions                                                │
│                                                                              │
│ bundles/base-spine.yaml                             rewrite → cordis YAML  │
│ profiles/web-standard.yaml                          rewrite → cordis YAML  │
│                                                                              │
│ lca/layer4_app/composer.py                          rewrite isolate scope  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 插件系统：cordis

### 4.1 vendor 引入

```bash
# 从 ~/taiyi-agent 复制三个 vendor 源码到 vendor/ 下
cp -r ~/taiyi-agent/vendor/cordis/src/cordis      vendor/cordis/src/
cp -r ~/taiyi-agent/vendor/cosmokit/src/cosmokit  vendor/cosmokit/src/
cp -r ~/taiyi-agent/vendor/schemastery/src/schemastery vendor/schemastery/src/
```

`pyproject.toml` 加 uv path 依赖：

```toml
[tool.uv.sources]
taiyi-cordis      = { path = "vendor/cordis/src" }
taiyi-cosmokit    = { path = "vendor/cosmokit/src" }
taiyi-schemastery = { path = "vendor/schemastery/src" }
```

### 4.2 公共 import 面

```python
# 唯一稳定 import path
from cordis import (
    Context, Service, Plugin, plugin,                  # 核心
    EventsService, Effect, DisposableList,            # 事件 + 副作用
    RegistryService, ReflectService, LoggerService,   # 内置服务
)
```

LCA 不再 re-export `cordis.*`——所有 `@plugin` 装饰 + Service 都从 `cordis` 直接 import。

### 4.3 标准插件形状

```python
# lca/plugins/llm/__init__.py
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel

class Config(BaseModel):
    model_config = {"extra": "forbid"}
    default_provider: str = "mock"

@plugin(name="lca-llm-service", inject=[])
async def setup(ctx, config: Config):
    """llm capability 的 Service Definition。

    LlmService 保持 plain class(LLMAdapter)——它不跟 ctx 生命周期绑定，
    所以不继承 cordis.Service。需要 auto-dispose 的资源类才继承。
    """
    from lca.layer0_infra.capability.llm import LlmService

    service = LlmService()
    ctx.provide("llm", service)
```

**LCA 保留原则**：`LlmService` / `ToolsService` / `SessionService` 等 Service Definition **不继承 `cordis.Service`**——它们是长寿命的注册表，绑定到 fiber 生命周期自动消失。`cordis.Service` 留给网络连接、DB、Cod 客户端这类需要 dispose 的。

### 4.4 Config 校验

cordis 用 Standard Schema（Pydantic v2 的 `model_config = {"extra": "forbid"}` 已经合规）；Loader 在每个 plugin 启动前调用 `Config['~standard'].validate(config)`，失败抛 `ValidationError`。

LCA 的 capability 清单（`SeamKey` 枚举）的"字段名"在 cordis 上变成 `inject`（依赖） + `provides`（提供）的语义对应：

| 旧 `SeamKey` | 新 `inject` / `provides` |
|---|---|
| `LLM` (`"llm"`) | provides `"llm"` |
| `SANDBOX` (`"sandbox"`) | provides `"sandbox"` |
| `MEMORY` (`"memory"`) | provides `"memory"` |
| `STATE_STORE` (`"state_store"`) | provides `"state_store"` |
| `SEARCH` (`"search"`) | provides `"search"` |
| `TOOLS` (`"tools"`) | provides `"tools"` |
| `TRANSPORT` (`"transport"`) | provides `"transport"` |
| `SKILLS` (`"skills"`) | provides `"skills"` |
| `FILE_STORE` (`"file_store"`) | provides `"file_store"` |
| `OBSERVABILITY` (`"observability"`) | provides `"observability"` |

`lca/contracts/mechanisms/capability.py` 保留，`SeamKey` 改名为 `CapabilityKey`（一致性）；`REQUIRED_SEAM_KEYS` 改名为 `REQUIRED_CAPABILITY_KEYS`。

---

## 5. 删除清单

| 路径 | 动作 | 原因 |
|---|---|---|
| `lca/layer0_infra/plugin/kernel/` | 删除 | cordis 替代 |
| `lca/layer0_infra/plugin/loader/` | 删除 | cordis.Loader 替代 |
| `lca/layer0_infra/plugin/include/` | 删除 | cordis.Loader.load_yaml 替代 |
| `lca/layer0_infra/plugin/scope/` | 删除 | cordis.Context.scope 替代 |
| `lca/layer0_infra/plugin/expr/` | 删除 | cordis.Loader.interpolate 替代 |
| `lca/layer0_infra/plugin/builtins/` | 删除 | cordis.Fiber.effect 替代 |
| `lca/layer0_infra/plugin/_test_plugins/` | 删除 | 依赖 `PluginConfig`，删后整个目录无意义 |
| `lca/harness/kernel/` | 删除 | cordis 替代 |
| `lca/harness/profile/boot.py` | 重写为 cordis 包装 | 保留 `boot_profile(Path, *, check_seam_completeness)` 签名（`check_seam_completeness` 改为 no-op 提示） |
| `lca/contracts/harness/plugin.py` | 拆 | 删 `Manifest`/`ExtensionPoint`/`CapabilityGrant`/`ScopeKind`/`PluginKind`/`ProviderMode`；**保留 `PluginContext` Protocol**（用于 compat/迁移期） |
| `lca/contracts/mechanisms/plugin.py` | 拆 | 删 `Plugin` Protocol；**保留 `PluginConfig` Pydantic 基类** |
| `lca/contracts/mechanisms/seam.py` | 拆 | 删 `SeamRole`/`SeamDeclaration`/`SeamRegistry`/`seam`/`validate_all_seams`；**保留 `consume()`** |
| `lca/plugins/seam_definitions/` | 删除 | cordis 不需要 |
| `lca/harness/middleware/registry.py` | 重写 | `COGNITIVE_POINTS` 10 点表迁移到 cordis event 名（`agent.before_step` 等）的 map |

---

## 6. 插件集重组

### 6.1 21 → 18 个 `@plugin`

| # | Plugin | 决策 | 新位置 |
|---|---|---|---|
| 1 | `llm_service` | ✅ 保留 | `lca/plugins/llm/__init__.py` |
| 2 | `llm_provider` | ✅ 保留 | `lca/plugins/llm/provider.py` |
| 3 | `tools_service` | ✅ 保留 | `lca/plugins/tools/__init__.py` |
| 4 | `session_service` | ✅ 保留 + 合并 agent_service | `lca/plugins/session/__init__.py` |
| 5 | `system_prompt` | ✅ 保留 | `lca/plugins/system_prompt/__init__.py` |
| 6 | `transport_service` | ✅ 保留 | `lca/plugins/transport/__init__.py` |
| 7 | `skills_service` | ✅ 保留 | `lca/plugins/skills/__init__.py` |
| 8 | `file_store_service` | ✅ 保留 | `lca/plugins/file_store/__init__.py` |
| 9 | `observability_service` | ✅ 保留 | `lca/plugins/observability/__init__.py` |
| 10 | `sandbox_service` | ✅ 保留 | `lca/plugins/sandbox/__init__.py` |
| 11 | `memory_service` | ✅ 保留 | `lca/plugins/memory/__init__.py` |
| 12 | `search_service` | ✅ 保留 | `lca/plugins/search/__init__.py` |
| 13 | `state_store_service` | ✅ 保留 | `lca/plugins/state_store/__init__.py` |
| 14 | `loop_cognitive` | ✅ 保留 | `lca/plugins/agent_loop/cognitive.py` |
| 15 | `loop_dsh_bridge` | ✅ 保留（过渡） | `lca/plugins/agent_loop/dsh_bridge.py` |
| 16 | `loop_replay` | ✅ 保留 | `lca/plugins/agent_loop/replay.py` |
| 17 | `gateway_starlette` | ✅ 保留 | `lca/plugins/gateways/starlette.py` |
| 18 | `loop_intervention_policy` | 🔄 改名 | `lca/plugins/guards/loop_intervention.py` |
| 19 | `budget_policy` | 🔄 改名 | `lca/plugins/guards/step_budget.py` |
| 20 | `agent_service` | 🔀 合并入 session_service | — |
| 21 | `seam_definitions` | ❌ 删除 | — |

### 6.2 路径约定

```
lca/plugins/
├── llm/
│   ├── __init__.py        # @plugin llm_service
│   └── provider.py        # @plugin llm_provider
├── tools/
├── session/               # 提供 SessionService + AgentEvents facade
├── system_prompt/
├── transport/
├── skills/
├── file_store/
├── observability/
├── sandbox/
├── memory/
├── search/
├── state_store/
├── agent_loop/
│   ├── cognitive.py
│   ├── dsh_bridge.py
│   └── replay.py
├── gateways/
│   └── starlette.py
└── guards/
    ├── loop_intervention.py
    └── step_budget.py
```

多文件 plugin（`llm/`、`agent_loop/`）的入口模块用 `@plugin(name="lca-llm-service")` 标记；其他模块可以激活时通过 `cordis.loader.Loader` 的模块路径引用。

### 6.3 agent_service 合并入 session_service

原 `agent_service` 是 `session.append` 的 typed facade，6 个方法：

| 旧方法 | 新方法（session_service） |
|---|---|
| `record_assistant_response(store, turn, step, content, tool_calls)` | `record_assistant_message(session_id, turn, step, content, tool_calls)` |
| `record_tool_call(store, call_id, tool_name, args)` | `record_tool_call(session_id, call_id, tool_name, args)` |
| `record_tool_result(store, call_id, result)` | `record_tool_result(session_id, call_id, result)` |
| `record_turn_boundary(store, turn, kind)` | `record_turn_start(session_id, turn)` / `record_turn_end(session_id, turn)` |
| `record_step_boundary(store, turn, step, kind)` | `record_step_start(session_id, turn, step)` / `record_step_end(session_id, turn, step)` |
| `record_xxx(...)` (其他) | ... |

`SessionService` 加一组 `record_*` 方法。

**调用点扫描（P5 必跑）**：`rg "agent_service"` + `rg "agent\.service"` + `rg "AgentService"` 找全 caller（包括 `bundles/base-spine.yaml:65-67` 的 `lca.agent.service` 引用）。指定 LLM / Runtime / loop_cognitive / loop_dsh_bridge / loop_replay 等。

---

## 7. bundle / profile 改写

### 7.1 `bundles/base.yaml`（替代 `base-spine.yaml`）

cordis 的 `Entry` dataclass 用 `id` 作主键；`$module` 是 LCA 层加的扩展（cordis 解析器本身从 `name` 反查 module，但 LCA 走自己的 include 协议）。YAML 实际形态：

```yaml
# bundles/base.yaml
plugins:
  - id: lca-llm-service
    name: lca-llm-service
    $module: lca.plugins.llm
  - id: lca-llm-provider
    name: lca-llm-provider
    $module: lca.plugins.llm.provider
    inject: ["llm"]
    config:
      mode: auto
  - id: lca-tools-service
    name: lca-tools-service
    $module: lca.plugins.tools
  - id: lca-session-service
    name: lca-session-service
    $module: lca.plugins.session
  - id: lca-system-prompt-service
    name: lca-system-prompt-service
    $module: lca.plugins.system_prompt
  - id: lca-transport-service
    name: lca-transport-service
    $module: lca.plugins.transport
  - id: lca-skills-service
    name: lca-skills-service
    $module: lca.plugins.skills
  - id: lca-file-store-service
    name: lca-file-store-service
    $module: lca.plugins.file_store
  - id: lca-observability-service
    name: lca-observability-service
    $module: lca.plugins.observability
  - id: lca-sandbox-service
    name: lca-sandbox-service
    $module: lca.plugins.sandbox
  - id: lca-memory-service
    name: lca-memory-service
    $module: lca.plugins.memory
  - id: lca-search-service
    name: lca-search-service
    $module: lca.plugins.search
  - id: lca-state-store-service
    name: lca-state-store-service
    $module: lca.plugins.state_store
```

**注意**：cordis 自己解析 YAML 时需要 `id` 是主键（`Loader._is_entry_dict` 启发式）；`$module` 是 LCA 抽象——`lca.harness.profile.boot()` 重新构造的 thin wrapper 读 `$module` 后用 `importlib.import_module()` 解析模块路径，再交给 cordis 的 `Loader.load()` 时，把 `id` + `inject` + `config` 留给 cordis，模块引用自己挂上。

### 7.2 `bundles/web-app.yaml`

```yaml
plugins:
  - id: lca-loop-cognitive
    name: lca-loop-cognitive
    $module: lca.plugins.agent_loop.cognitive
  - id: lca-gateway-starlette
    name: lca-gateway-starlette
    $module: lca.plugins.gateways.starlette
  - id: lca-guard-loop-intervention
    name: lca-guard-loop-intervention
    $module: lca.plugins.guards.loop_intervention
  - id: lca-guard-step-budget
    name: lca-guard-step-budget
    $module: lca.plugins.guards.step_budget
```

bundle **继承**不复用 cordis 自带 `$patch` 机制；LCA 层用 `merge_bundles`（`cordis.loader.merge_bundles`）拼——`base.yaml` → `web-app.yaml` 顺序扩展。

### 7.3 `profiles/web-standard.yaml` 改写

```yaml
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch: []
```

---

## 8. `lca/layer4_app/composer.py` 重写

### 8.1 `_isolate_agent_scope` 改动

cordis 的 `Context.isolate(label, callback)` 是**回调式**——它不是 async context manager；async context manager 是 `Context.scope(label)`（见 `cordis/context.py:339`）。当前 `composer.py:_isolate_agent_scope` 的语义是构造一个子 scope 并 shadow 服务实例，所以正确模式是 `Context.scope(label)`：

```python
# before
def _isolate_agent_scope(parent: ScopedPluginHost, role: str) -> ScopedPluginHost:
    child = parent.fork(ScopeKind.AGENT, f"agent:{role}")
    child.provide(handle, "llm", LlmService())  # 三参数
    child.provide(handle, "tools", ToolsService())
    child.provide(handle, "transport", TransportService())
    # memory / state_store 沿用父（深拷贝 providers）
    ...
    return child

# after
async def _isolate_agent_scope(parent: Context, role: str) -> Context:
    async with parent.scope(f"agent:{role}") as child:
        child.provide("llm", LlmService())
        child.provide("tools", ToolsService())
        child.provide("transport", TransportService())
        # memory / state_store 沿用父（深拷贝 providers）
        ...
        yield child
```

**重要语义**：cordis 的 `Context.scope(label)` 只是 scope-tracking + 共享 root；它**不**自动 shadow 服务实例。LCA 的 "每 agent 一份独立 LlmService" 的语义需要：
- 显式 `child.provide("llm", LlmService())` 覆盖父
- 由 `async with parent.scope(...)` 的释放钩子卸载

让 child 保留父的 memory / state_store（providers 列表）需要 `parent.require("memory").providers` → 拷贝构造新 `MemoryService()`。

### 8.2 `ScopedPluginHost` 的使用点

spec 初稿说"约 6 处 `current_scope()`"——**错的**。`rg "current_scope\("` 返回空。实际引用 `ScopedPluginHost` 接口的位置（`scope.resolve` / `scope.fork` / `scope.provide` / `wrap`）：

| 文件 | 模式 | 替代 |
|---|---|---|
| `lca/layer4_app/composer.py:466` | `parent.fork(ScopeKind.AGENT, ...)` | `parent.scope("agent:{role}")` |
| `lca/layer4_app/composer.py:496-499` | `child.provide(handle, ...)` | `child.provide(key, value)` |
| `lca/layer4_app/api.py:105` | `isinstance(x, ScopedPluginHost)` | `isinstance(x, Context)` |
| `gateway/app.py:149-153` | `ScopedPluginHost.wrap(host, ScopeKind.DEPLOYMENT, ...)` | `Context.wrap(host)` + `setup_logging()` |
| `lca/plugins/loop_cognitive/__init__.py:99` | `plugin_scope.resolve("llm")` | `ctx.inject("llm")` |
| `lca/plugins/loop_cognitive/__init__.py:105` | `plugin_scope.resolve("tools")` | `ctx.inject("tools")` |
| `lca/plugins/loop_dsh_bridge/__init__.py` | `scope.resolve("session_store")` / `scope.resolve("dsh_settings")` | `ctx.inject(...)` |
| `lca/plugins/loop_replay/__init__.py` | `scope.resolve("session_store")` | `ctx.inject(...)` |
| `lca/harness/diagnostics/tree.py` | tree walker over `ScopedPluginHost` | 重写为 cordis `Context` walker |

### 8.3 mount / provide 翻译

```python
# before
ctx.mount(handle, "llm", service)              # 三参数 (handle, key, value)
ctx.mount(handle, "llm", service, check=fn)    # 四参数

# after
ctx.provide("llm", service)                    # 二参数 (key, value)
# check predicate via Service.check classmethod（只有继承 cordis.Service 的类才需要）
```

`handle` 的概念在 cordis 里由 `ctx.fiber.effect` 自动管理——`provide` 不需要显式 handle；插件 setup 里所有写入 `ctx.provide(...)` / `ctx.effect(...)` / `ctx.on(...)` 都是 fiber-owned，卸载时自动撤销。

### 8.4 `consume()` 保留

`lca/contracts/mechanisms/seam.py` 的 `consume(definition, provider, consumer)` 函数（composition-time gate）**保留**。3 个 production 调用点（`composer.py:266,268,365` / `brain/default_factory.py:32` / `sandbox/runtime_scope.py:41`）+ 4 个测试文件不变。`SeamRole`/`SeamDeclaration`/`SeamRegistry`/`seam`/`validate_all_seams` 删掉。

### 8.5 `PluginConfig` 保留

`lca/contracts/mechanisms/plugin.py` 的 `PluginConfig` Pydantic 基类（`extra="forbid"` 默认）保留。`Plugin` Protocol 删（cordis 的 `@plugin` 装饰器替代）。

---

## 9. 迁移序列

| Phase | 内容 | 验证 |
|---|---|---|
| **P0** | vendor 引入 cordis + cosmokit + schemastery（`uv sync` 跑通 + `pyproject.toml` 加 `[tool.uv.sources]`） | `uv run python -c "from cordis import Context, plugin"` |
| **P1** | 删 `lca/layer0_infra/plugin/`（含 `_test_plugins/`）+ `lca/harness/kernel/` | `rg -l lca.layer0_infra.plugin` 空 |
| **P2** | 拆 `lca/contracts/{harness/plugin.py, mechanisms/plugin.py, mechanisms/seam.py}` 三处：删 LCA seam 抽象，保留 `consume()` / `PluginConfig` | `rg "PluginManifest\|ExtensionPoint\|CapabilityGrant\|ScopeKind\|PluginKind\|ProviderMode\|SeamDeclaration\|SeamRegistry\|seam\b"` 仅命中 docstring；`rg "from lca.contracts.mechanisms.seam import consume"` 仍能 import |
| **P3** | `lca/harness/middleware/registry.py` 10 点 `COGNITIVE_POINTS` 重写为 cordis event 名 map | `tests/test_middleware.py` |
| **P4** | `lca/harness/profile/boot.py` 重写为 cordis.Loader 薄包装（保留 `boot_profile(path, *, check_seam_completeness: bool = True)` 签名；now no-op 警告） | `gateway/app.py:138` + `tests/harness/test_phase_a_integration.py:225` 跑通 |
| **P5** | 21 个 plugin 改写为 `@plugin` 形式（一次提交） | `uv run pytest lca/plugins/ tests/test_plugin_*.py` |
| **P6** | bundle / profile YAML 改写（`bundles/base.yaml` + `bundles/web-app.yaml` + `profiles/web-standard.yaml`） | `lca-ops status` + `lca-ops inspect-tree` |
| **P7** | `composer.py` + `loop_cognitive` + `loop_dsh_bridge` + `loop_replay` + `gateway/app.py` + `lca/layer4_app/api.py` + `lca/harness/diagnostics/tree.py` 改写（`scope.resolve` → `ctx.inject`；`scope.fork` → `ctx.scope`；`scope.provide` → `ctx.provide`） | `uv run pytest lca/layer4_app/ tests/harness/` + `examples/pluggability_demo/` |
| **P8** | 端到端：`scripts/run_team_mode.py` 跑通真 e2e | Agent reply 在 journal |
| **P9** | `loop_dsh_bridge` 重新挂上（之前在 P5 跑过 stub） | `lca-ops logs` 看 dsh bridge 记录 |

每 phase 必跑：
- `uv run ruff check --fix <改动路径> && uv run ruff format <改动路径>`
- `uv run pytest --no-cov <对应测试> -q`
- `uv run lint-imports`（P1、P2、P6 必跑）

P3 / P5 必跑：
- `uv run vulture lca --min-confidence 80`（确认删除干净）

P4 / P6 必跑：
- `uv run mypy lca/layer4_app`（签名变了）

---

## 10. 验证矩阵

| 关注点 | 命令 |
|---|---|
| 启动链路 | `lca-ops status` / `lca-ops logs` |
| 插件树 | `lca-ops inspect-tree`（对齐 dsh `--dump-config`） |
| Provider dispatch | `tests/test_llm_provider*.py` |
| Session 事件 | `tests/test_session_service.py` + `tests/test_journal_*.py` |
| Agent 隔离 | `tests/test_compose_*.py` + `tests/test_isolate_agent_scope.py` |
| Bundle 装载 | `tests/test_bundle_loading.py` |
| DSH bridge | `tests/test_dsh_bridge*.py` |
| 端到端 | `scripts/run_team_mode.py` + 看 journal |
| 协议守护 | `tests/test_protocol_impl.py`（Manifest 删除后只对 Protocol 检查） |

---

## 11. 风险分析

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| `composer.py` + 5 个 plugin + `gateway/app.py` + `api.py` `ScopedPluginHost` / `scope.resolve` 引用漏改 | 高 | 阻塞 | P7 阶段明确列 9 个调用点（见 §8.2 表） |
| `consume()` 保留，但 `seam.py` 拆分后忘记 re-export | 中 | 阻塞 | P2 阶段 `from lca.contracts.mechanisms.seam import consume` 跑通 |
| `PluginConfig` 保留，但 `plugin.py` 拆分后忘记 re-export | 中 | 阻塞 | P2 阶段 `from lca.contracts.mechanisms.plugin import PluginConfig` 跑通 |
| `lca/harness/middleware/registry.py` 拆 `COGNITIVE_POINTS` 时漏掉中间件 plugin 引用 | 中 | 阻塞 | P3 阶段先 `rg COGNITIVE_POINTS` 找全 |
| `_isolate_agent_scope` 改写后 `Context.scope(label)` 不创建新 `LlmService` 实例 | 高 | 行为破坏 | 显式 `child.provide("llm", LlmService())` 覆盖父；`tests/test_compose_*.py` 用两个并发 agent 验证（不能互相覆盖） |
| `bundles/base-spine.yaml` → `bundles/base.yaml` 改名打破外部引用 | 低 | 持续集成 | P6 阶段 `rg "base-spine"` 全仓扫（已知引用：`profiles/web-standard.yaml`、`tests/test_phase_a_integration.py`、`docs/superpowers/specs/2026-08-16-plugin-tree-runtime-design.md`、`lca-ops` 脚本） |
| `loop_dsh_bridge` 内部 plugin scope resolve 改写时回归到旧 `lca.harness.kernel` 路径 | 中 | 阻塞 | P7 阶段把 dsh_bridge 放进 `tests/test_loop_dsh_bridge.py` 隔离测试 |
| `lca_harness.profile.boot()` 公开 API 仍被外部脚本调用 | 低 | 阻塞 | P4 阶段保留 `boot_profile(path, *, check_seam_completeness)` 签名（`check_seam_completeness` 变为 no-op 警告）；`gateway/app.py:138` 和 `tests/harness/test_phase_a_integration.py:225` 跑通 |
| `cordis.Loader.load_yaml` 实际不存在，需要 LCA 层包装 | 中 | 阻塞 | P0 阶段先 `rg "load_yaml" cordis/` 验证；不存在则 LCA 层用 `yaml.safe_load` + `cordis.loader.Loader.load()` |
| vendor 同步：taiyi 未来更新 cordis 时 LCA 同步 | 低 | 长期 | 写 `scripts/sync_vendor.sh` 借鉴 taiyi 同步协议 |
| `Hook` 名字冲突（cordis 导出 `Hook` class；LCA `lca/contracts/mechanisms/__init__.py` 也有 `Hook` Protocol） | 低 | 命名冲突 | 所有 LCA 内部继续 `from lca.contracts.mechanisms import Hook`；不 re-export cordis 符号；如要交叉 import 显式 `from cordis import Hook as CordisHook` |

---

## 12. 不在范围（明确 YAGNI）

- 100+ dsh 包的 Python port（subagent / sandbox / LSP / MCP / ACP / compaction / skill / goal / workflow / jobs / todo / plan / preset / guard / hooks / session-query / settings / credentials / attachment / fs / lsp / terminal / code-runtime / shell / subprocess / e2b / feedback / context / identity / interaction / web / storage / workspace / boot / sdk / examples / support / util / typert）
- 不动 `lca/contracts/protocols/` 的 16 个 `@runtime_checkable Protocol`
- 不改 Journal 事实源契约
- 不改 L4 公共面 `Agent` / `Team` / `TeamLead` / `Pipeline`
- 不重写 lobehub 集成（patches 源不动）
- 不重写 gateway 的 HTTP 路由形状（仅内部 mount 改成 cordis 加载）

---

## 13. 验收

- `uv run lca-ops status` 跑通，所有 capability 加载成功
- `uv run lca-ops inspect-tree` 输出 cordis 风格的插件树
- `uv run pytest --no-cov` 全过（real_llm 跳过）
- `scripts/run_team_mode.py` 起真 e2e，journal 落一条 agent reply
- `rg -l lca.layer0_infra.plugin` 空（in-house kernel 完全删除）
- `rg "PluginManifest\|ExtensionPoint\|CapabilityGrant\|ScopeKind\|PluginKind\|ProviderMode\|SeamDeclaration\|SeamRegistry\|SeamRole"` 仅命中 docstring
- `rg "ScopedPluginHost\|scope\.resolve\|scope\.fork\|ScopeKind\."` 仅命中 docstring
- `from lca.contracts.mechanisms.seam import consume` 仍能 import
- `from lca.contracts.mechanisms.plugin import PluginConfig` 仍能 import
- `uv run vulture lca --min-confidence 80` 干净
