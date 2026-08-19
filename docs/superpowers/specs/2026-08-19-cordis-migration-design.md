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
- 21 个 `lca/plugins/*` 改写为 `@plugin` 形式（Tier-1 Definition）
- **30+ Tier-2 Provider plugins** 抽出到 `lca/plugins/providers/{seam}/{provider}.py`（替换 `lca/layer4_app/capability_boot.py:mount_default_providers()` 硬编码）
- **15+ Tier-3 Behavior plugins** 抽出到 `lca/plugins/{brain,reasoner,synthesizer,team,guards,dsh}/...`（替换 `composer.py:_resolve_component` + `lca/contracts/models/team/team_coordination.py` 硬编码）
- `bundles/base.yaml` 包含 Tier-1 + Tier-2 entries；`bundles/web-app.yaml` 追加 Tier-3 entries
- `lca/layer4_app/composer.py` 全部 `import X; X()` 形式改为 `ctx.inject(...)`/`ctx.provide(...)`
- `lca/layer4_app/capability_boot.py` 删掉（被 Tier-1 plugin 集合完全替代）
- vendor 引入 `taiyi-cordis` / `taiyi-cosmokit` / `taiyi-schemastery`

**三 Tier 落实"插件贯彻"**：

```
Tier-1 Definition (~21)
  ↓ 注：Definition 仅是接口 + 空注册表
Tier-2 Provider (~30+)
  ↓ 注：每个 seam 至少 1 个 default；可用 patch 替换
Tier-3 Behavior (~15+)
  ↓ 注：Brain / Loop / Team / Middleware 全部 plugin
@plugin setup
  ↓
cordis Context → L4 组合根只 inject
```

**L4 组合根 = `ctx.inject(...)` 唯一合法组装路径**。任何 `from X import Y; Y(...)` 直接构造都视为违规。`lca.layer4_app.capability_boot.py` 全删。

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
# lca/plugins/llm_service.py
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
| `lca/plugins/{llm,tools,transport,skills,file_store,observability,sandbox,memory,search,state_store}_service/__init__.py` | 改为单文件 module | 见 §6.2 |
| `lca/plugins/agent_service/__init__.py` | 合并入 `lca/layer0_infra/session/` | 见 §6.3 |
| `lca/plugins/loop_intervention_policy/__init__.py` | 改名 `lca/plugins/guards/loop_intervention.py` | 见 §6.1 |
| `lca/plugins/budget_policy/__init__.py` | 改名 `lca/plugins/guards/step_budget.py` | 见 §6.1 |

---

## 6. 插件集重组

### 6.1 21 → 18 个 `@plugin`（module-形状）— Tier-1 Definition

**Tier-1 仅是入口；Tier-2/3 见 §6.3**（必备，否则不算"插件贯彻"）。

| # | Plugin | 决策 | 新位置（plugin module） | Service 类归口 |
|---|---|---|---|---|
| 1 | `llm_service` | ✅ 保留 | `lca/plugins/llm_service.py` | `lca/layer0_infra/capability/llm.py` |
| 2 | `llm_provider` | ✅ 保留 | `lca/plugins/llm_provider.py` | 同上 |
| 3 | `tools_service` | ✅ 保留 | `lca/plugins/tools_service.py` | `lca/layer0_infra/capability/tools.py` |
| 4 | `session_service` | ✅ 保留 + 合并 agent_service | `lca/plugins/session_service.py` | `lca/layer0_infra/session/{service,events_assistant,events_tool,events_turn,events_step}.py` |
| 5 | `system_prompt` | ✅ 保留 | `lca/plugins/system_prompt.py` | `lca/layer0_infra/system_prompt/{sections,assembler,service}.py` |
| 6 | `transport_service` | ✅ 保留 | `lca/plugins/transport_service.py` | `lca/layer0_infra/capability/transport.py` |
| 7 | `skills_service` | ✅ 保留 | `lca/plugins/skills_service.py` | `lca/layer0_infra/capability/skills.py` |
| 8 | `file_store_service` | ✅ 保留 | `lca/plugins/file_store_service.py` | `lca/layer0_infra/capability/files.py` |
| 9 | `observability_service` | ✅ 保留 | `lca/plugins/observability_service.py` | `lca/layer0_infra/capability/observability.py` |
| 10 | `sandbox_service` | ✅ 保留 | `lca/plugins/sandbox_service.py` | `lca/layer0_infra/capability/sandbox.py` |
| 11 | `memory_service` | ✅ 保留 | `lca/plugins/memory_service.py` | `lca/layer0_infra/capability/memory.py` |
| 12 | `search_service` | ✅ 保留 | `lca/plugins/search_service.py` | `lca/layer0_infra/capability/search.py` |
| 13 | `state_store_service` | ✅ 保留 | `lca/plugins/state_store_service.py` | `lca/layer0_infra/capability/state_store.py` |
| 14 | `loop_cognitive` | ✅ 保留 | `lca/plugins/loop_cognitive.py` | `lca/layer3_agent/loop_cognitive.py` |
| 15 | `loop_dsh_bridge` | ✅ 保留（过渡） | `lca/plugins/loop_dsh_bridge.py` | `lca/layer0_infra/dsh/` |
| 16 | `loop_replay` | ✅ 保留 | `lca/plugins/loop_replay.py` | `lca/layer2_runtime/loop_replay.py` |
| 17 | `gateway_starlette` | ✅ 保留 | `lca/plugins/gateway_starlette.py` | `gateway/` |
| 18 | `loop_intervention_policy` | 🔄 改名 | `lca/plugins/guards/loop_intervention.py` | `lca/layer2_runtime/loop_intervention_mw.py` |
| 19 | `budget_policy` | 🔄 改名 | `lca/plugins/guards/step_budget.py` | `lca/layer2_runtime/budget_policy.py` |
| 20 | `agent_service` | 🔀 合并入 session_service | — | — |
| 21 | `seam_definitions` | ❌ 删除 | — | — |

### 6.2 路径约定：**module per plugin，唯一保留 package 是 `guards/`**

**第一原则**：「plugin 文件 = `@plugin` 装饰 + 1-N 行 setup 函数」。**Service 类不居住在 plugin 文件里**——它住在 `lca/layer0_infra/capability/{name}.py` 或 `lca/layer2_runtime/` 或 `lca/layer3_agent/` 真正属于它的归口模块。plugin 文件只是把 service 挂到 ctx 的接线。

```python
# lca/plugins/llm_service.py  — 4 行
from cordis import plugin
from lca.layer0_infra.capability.llm import LlmService

@plugin(name="lca-llm-service")
async def setup(ctx, config):
    ctx.provide("llm", LlmService())
```

```python
# lca/plugins/system_prompt.py  — 4 行（原 195 行压成 4 行）
from cordis import plugin
from lca.layer0_infra.system_prompt.service import SystemPromptService

@plugin(name="lca-system-prompt-service")
async def setup(ctx, config):
    ctx.provide("system_prompt", SystemPromptService())
```

**plugin 文件大小约束**：单文件 ≤ 50 行。超过 50 行 = 把 service 拆出去。

**`guards/` 唯一保留 package**：2 个 guard 共享 `audit/rollback` 辅助概念，可能共出 `_helpers.py`。

```
lca/plugins/
├── llm_service.py            # 4 行
├── llm_provider.py           # ~30 行（含 Config pydantic 校验）
├── tools_service.py
├── session_service.py        # 4 行 + import lca.layer0_infra.session.service
├── system_prompt.py          # 4 行
├── transport_service.py
├── skills_service.py
├── file_store_service.py
├── observability_service.py
├── sandbox_service.py
├── memory_service.py
├── search_service.py
├── state_store_service.py
├── loop_cognitive.py
├── loop_dsh_bridge.py
├── loop_replay.py
├── gateway_starlette.py
└── guards/                   # 唯一 package
    ├── __init__.py
    ├── loop_intervention.py
    └── step_budget.py
```

bundle YAML `$module` 字段相应改为模块路径：

```yaml
- id: lca-llm-service
  name: lca-llm-service
  $module: lca.plugins.llm_service      # 不是 lca.plugins.llm
```

### 6.3 Plugin 三层分级（实现 "everything is a plugin"）

DSH 与 LCA 的"插件贯彻"实际是**三层**：

| Tier | 角色 | 数量（约） | 例子 |
|---|---|---|---|
| **Tier-1: Definition Plugin** | 声明 seam + 挂载 Definition 服务 | 21 | `lca.plugins.llm_service` 挂 `LlmService` |
| **Tier-2: Provider Plugin** | 实现 Definition 接口，挂载到 Definition | 30+ | `lca.plugins.providers.llm.mock` 注册 `MockLLMAdapter` |
| **Tier-3: Behavior Plugin** | 业务行为（Brain / Loop / Coordination / Middleware） | 15+ | `lca.plugins.brain.modular` 装 `ModularBrain` |

**第一轮 spec 只覆盖 Tier-1**。"完全贯彻"必须把 Tier-2 + Tier-3 也 plugin 化。

#### Tier-2 Provider Plugin 清单（当前硬编码，要 plugin 化）

| Seam | Provider plugins（每个一个 plugin） |
|---|---|
| `llm` | `lca.plugins.providers.llm.mock` / `.real` / `.pi_ai` / `.deepseek` |
| `memory` | `lca.plugins.providers.memory.simple` / `.redis` / `.vector` |
| `state_store` | `lca.plugins.providers.state_store.memory` / `.redis` / `.sqlite` |
| `search` | `lca.plugins.providers.search.tavily` / `.bing` / `.serpapi` |
| `tools` | `lca.plugins.providers.tools.g2a_factory` / `.office_factory` |
| `transport` | `lca.plugins.providers.transport.internal` / `.a2a` / `.mcp` |
| `skills` | `lca.plugins.providers.skills.disk` / `.remote` |
| `file_store` | `lca.plugins.providers.file_store.local` / `.s3` |
| `observability` | `lca.plugins.providers.observability.console` / `.langfuse` / `.otel` |
| `sandbox` | `lca.plugins.providers.sandbox.local` / `.e2b` / `.docker` |
| `workspace` | `lca.plugins.providers.workspace.local` / `.remote` |

**plugin 形状**（统一）：

```python
# lca/plugins/providers/llm/mock.py
from cordis import plugin

@plugin(name="lca-llm-provider-mock", inject=["llm"])
async def setup(ctx, config):
    """Register the mock LLM adapter as the default provider."""
    from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
    ctx.inject("llm").register("mock", MockLLMAdapter(), activate=True)
```

每个 Tier-2 plugin 声明 `inject=["<seam_key>"]`，`config` 包含 `mode: auto|force` 等选择。Bundle YAML 由 Tier-2 plugin 的存在/缺失决定哪些 provider 实际可用。

**bundle YAML 改写**（append-only，所有 default provider 都在）：

```yaml
# bundles/base.yaml
plugins:
  # Tier-1 Definitions
  - id: lca-llm-service
    $module: lca.plugins.llm_service
  - id: lca-memory-service
    $module: lca.plugins.memory_service
  # ... 其他 11 略

  # Tier-2 默认 Providers（每个 seam 至少 1 个 default）
  - id: lca-llm-provider-mock
    $module: lca.plugins.providers.llm.mock
    inject: ["llm"]
    config:
      mode: auto           # auto = real when LLM_API_KEY present, else mock
  - id: lca-memory-provider-simple
    $module: lca.plugins.providers.memory.simple
    inject: ["memory"]
  - id: lca-state-store-provider-memory
    $module: lca.plugins.providers.state_store.memory
    inject: ["state_store"]
  - id: lca-search-provider-tavily
    $module: lca.plugins.providers.search.tavily
    inject: ["search"]
  - id: lca-tools-provider-g2a
    $module: lca.plugins.providers.tools.g2a_factory
    inject: ["tools"]
  - id: lca-transport-provider-internal
    $module: lca.plugins.providers.transport.internal
    inject: ["transport"]
  - id: lca-skills-provider-disk
    $module: lca.plugins.providers.skills.disk
    inject: ["skills"]
  - id: lca-file-store-provider-local
    $module: lca.plugins.providers.file_store.local
    inject: ["file_store"]
  - id: lca-observability-provider-console
    $module: lca.plugins.providers.observability.console
    inject: ["observability"]
  - id: lca-sandbox-provider-local
    $module: lca.plugins.providers.sandbox.local
    inject: ["sandbox"]
  - id: lca-workspace-provider-local
    $module: lca.plugins.providers.workspace.local
    inject: ["workspace"]
```

**用户切换** = 删除/替换 bundle YAML 中的 Tier-2 entry，或者用 `profiles/web-app.yaml` 的 `patch` 删掉再 insert 新的。

#### Tier-3 Behavior Plugin 清单

| Behavior | Plugin |
|---|---|
| Brain 默认实现 | `lca.plugins.brain.modular`（装 `ModularBrain`） / `lca.plugins.brain.simple`（装 `SimpleBrain`） |
| Reasoner | `lca.plugins.reasoner.prompt` / `lca.plugins.reasoner.critic` |
| Synthesizer | `lca.plugins.synthesizer.concat` / `lca.plugins.synthesizer.streaming` |
| Loop Driver | `lca.plugins.loop_cognitive`（已有）/ `lca.plugins.loop_dsh_bridge` / `lca.plugins.loop_replay` |
| Team Coordination | `lca.plugins.team.pipeline` / `lca.plugins.team.fanout` / `lca.plugins.team.graph` / `lca.plugins.team.debate` / `lca.plugins.team.peer_relay` / `lca.plugins.team.peer_swarm` |
| Middleware / Guard | `lca.plugins.guards.loop_intervention`（已有）/ `lca.plugins.guards.step_budget` |
| DSH Bridge | `lca.plugins.dsh.bridge`（装 `build_harness_env` 工厂） |

**plugin 形状**（统一）：

```python
# lca/plugins/brain/modular.py
from cordis import plugin

@plugin(name="lca-brain-modular")
async def setup(ctx, config):
    """Mount the default ModularBrain strategy as the brain factory."""
    from lca.layer1_cognitive.brain.modular_brain import ModularBrain
    from lca.layer1_cognitive.brain.default_factory import brain_factory
    
    brain_factory.register("modular", ModularBrain)
    ctx.provide("brain_factory", brain_factory)
```

#### 替换 `composer.py:_resolve_component` 硬编码

旧的：
```python
# lca/layer4_app/composer.py:225 — 硬编码
def _resolve_component(...):
    brain = ModularBrain(...)  # 直接 import + 构造
    return brain
```

新的（plugin 化后）：
```python
# lca/layer4_app/composer.py — 一切来自 ctx
def _resolve_component(scope, ...):
    factory = scope.inject("brain_factory")
    return factory.resolve("modular", ...)
```

L4 组合根**只**通过 `ctx.inject(...)` 拿东西。任何 `import X; X()` 直接构造都视为违规。

### 6.4 agent_service 合并入 session_service

原 `agent_service` 是 `session.append` 的 typed facade，**5 个方法**（不是 6 个）：

| 旧方法（agent_service） | 新方法（session_service） |
|---|---|
| `record_assistant_response(store, turn, step, content, tool_calls)` | `record_assistant_message(session_id, turn, step, content, tool_calls)` |
| `record_tool_call(store, turn, step, call_id, tool_name, arguments_ref)` | `record_tool_call(session_id, turn, step, call_id, tool_name, arguments_ref)` |
| `record_tool_result(store, turn, step, call_id, success, result_ref, error)` | `record_tool_result(session_id, turn, step, call_id, success, result_ref, error)` |
| `record_turn_boundary(store, turn, event_type)` | `record_turn_start(session_id, turn)` / `record_turn_end(session_id, turn, reason)` |
| `record_step_boundary(store, turn, step, event_type)` | `record_step_start(session_id, turn, step)` / `record_step_end(session_id, turn, step)` |

**关键约束**：所有 `turn` / `step` / `arguments_ref` / `result_ref` / `error` / `event_type` 字段语义保留——它们是 surface event 上必须保留的字段（DSH `SessionEvent` 同构）。`store.append(...)` 内部化进 `SessionService`，`session_id` 替代 `store`（store 通过 `ctx.inject("session_store")` 内部获取）。

**Service 类拆 5 个文件**（与 5 个 record_* 方法对应）：

```
lca/layer0_infra/session/
├── __init__.py
├── service.py                   # SessionService（聚合面）
├── events_assistant.py          # record_assistant_message + AssistantResponded 构造
├── events_tool.py               # record_tool_call / record_tool_result + ToolCalled/ToolCompleted 构造
├── events_turn.py               # record_turn_start / record_turn_end + TurnStarted/TurnEnded 构造
├── events_step.py               # record_step_start / record_step_end + StepStarted/StepEnded 构造
└── surface.py                   # DSH surface event 投影（_project_message_accepted 等）
```

`SessionService` 内部持 4 个 `*_recorder` 子对象（`self.assistant = AssistantRecorder(self._store)`），`record_*` 委派。`lca/layer0_infra/session/service.py` 主体仍是 plugin setup 的归口。

**plugin module 形状**：

```python
# lca/plugins/session_service.py  — 4 行
from cordis import plugin
from lca.layer0_infra.session.service import SessionService

@plugin(name="lca-session-service")
async def setup(ctx, config):
    ctx.provide("session_service", SessionService())
```

**调用方迁移**：`agent_service.record_assistant_response(store, ...)` → `session_service.record_assistant_message(session_id, ...)`。

**调用点扫描（P5 必跑）**：
- `rg "agent_service"` 应只在 `lca/plugins/agent_service/`（删除目录）无引用
- `rg "agent\.service"` 应只在 `bundles/base-spine.yaml` 引用（之后 P6 同步改名）
- `rg "AgentService"` 找全 facade 引用
- 已知 caller：`lca/layer3_agent/` + `lca/layer2_runtime/` + `lca/plugins/loop_cognitive.py` + `lca/plugins/loop_dsh_bridge.py` + `lca/plugins/loop_replay.py` 都需要扫一遍

---

## 7. bundle / profile 改写

### 7.1 `bundles/base.yaml`（替代 `base-spine.yaml`）

cordis 的 `Entry` dataclass 用 `id` 作主键；`$module` 是 LCA 层加的扩展（cordis 解析器本身从 `name` 反查 module，但 LCA 走自己的 include 协议）。`$module` 路径对应 §6.2 的 module-per-plugin 形状 + §6.3 的 Tier-2 Provider 形状：

```yaml
# bundles/base.yaml
plugins:
  # ── Tier-1: Definitions ─────────────────────────────────────
  - id: lca-llm-service
    name: lca-llm-service
    $module: lca.plugins.llm_service
  - id: lca-tools-service
    name: lca-tools-service
    $module: lca.plugins.tools_service
  - id: lca-session-service
    name: lca-session-service
    $module: lca.plugins.session_service
  - id: lca-system-prompt-service
    name: lca-system-prompt-service
    $module: lca.plugins.system_prompt
  - id: lca-transport-service
    name: lca-transport-service
    $module: lca.plugins.transport_service
  - id: lca-skills-service
    name: lca-skills-service
    $module: lca.plugins.skills_service
  - id: lca-file-store-service
    name: lca-file-store-service
    $module: lca.plugins.file_store_service
  - id: lca-observability-service
    name: lca-observability-service
    $module: lca.plugins.observability_service
  - id: lca-sandbox-service
    name: lca-sandbox-service
    $module: lca.plugins.sandbox_service
  - id: lca-memory-service
    name: lca-memory-service
    $module: lca.plugins.memory_service
  - id: lca-search-service
    name: lca-search-service
    $module: lca.plugins.search_service
  - id: lca-state-store-service
    name: lca-state-store-service
    $module: lca.plugins.state_store_service

  # ── Tier-2: Default Providers（每个 seam 至少 1 个）──
  - id: lca-llm-provider-mock
    name: lca-llm-provider-mock
    $module: lca.plugins.providers.llm.mock
    inject: ["llm"]
    config:
      mode: auto
  - id: lca-memory-provider-simple
    name: lca-memory-provider-simple
    $module: lca.plugins.providers.memory.simple
    inject: ["memory"]
  - id: lca-state-store-provider-memory
    name: lca-state-store-provider-memory
    $module: lca.plugins.providers.state_store.memory
    inject: ["state_store"]
  - id: lca-search-provider-tavily
    name: lca-search-provider-tavily
    $module: lca.plugins.providers.search.tavily
    inject: ["search"]
  - id: lca-tools-provider-g2a
    name: lca-tools-provider-g2a
    $module: lca.plugins.providers.tools.g2a_factory
    inject: ["tools"]
  - id: lca-transport-provider-internal
    name: lca-transport-provider-internal
    $module: lca.plugins.providers.transport.internal
    inject: ["transport"]
  - id: lca-transport-provider-a2a
    name: lca-transport-provider-a2a
    $module: lca.plugins.providers.transport.a2a
    inject: ["transport"]
  - id: lca-transport-provider-mcp
    name: lca-transport-provider-mcp
    $module: lca.plugins.providers.transport.mcp
    inject: ["transport"]
  - id: lca-skills-provider-disk
    name: lca-skills-provider-disk
    $module: lca.plugins.providers.skills.disk
    inject: ["skills"]
  - id: lca-file-store-provider-local
    name: lca-file-store-provider-local
    $module: lca.plugins.providers.file_store.local
    inject: ["file_store"]
  - id: lca-observability-provider-console
    name: lca-observability-provider-console
    $module: lca.plugins.providers.observability.console
    inject: ["observability"]
  - id: lca-sandbox-provider-local
    name: lca-sandbox-provider-local
    $module: lca.plugins.providers.sandbox.local
    inject: ["sandbox"]
```

**注意**：cordis 自己解析 YAML 时需要 `id` 是主键（`Loader._is_entry_dict` 启发式）；`$module` 是 LCA 抽象——`lca.harness.profile.boot()` 重新构造的 thin wrapper 读 `$module` 后用 `importlib.import_module()` 解析模块路径，再交给 cordis 的 `Loader.load()` 时，把 `id` + `inject` + `config` 留给 cordis，模块引用自己挂上。

### 7.2 `bundles/web-app.yaml`

```yaml
plugins:
  # ── Tier-3: Behavior Plugins ──────────────────────────────
  # Brain / Reasoner / Synthesizer
  - id: lca-brain-modular
    name: lca-brain-modular
    $module: lca.plugins.brain.modular
  - id: lca-reasoner-prompt
    name: lca-reasoner-prompt
    $module: lca.plugins.reasoner.prompt
  - id: lca-synthesizer-concat
    name: lca-synthesizer-concat
    $module: lca.plugins.synthesizer.concat
  # Loop Driver
  - id: lca-loop-cognitive
    name: lca-loop-cognitive
    $module: lca.plugins.loop_cognitive
  - id: lca-loop-dsh-bridge
    name: lca-loop-dsh-bridge
    $module: lca.plugins.loop_dsh_bridge
  - id: lca-loop-replay
    name: lca-loop-replay
    $module: lca.plugins.loop_replay
  # Team Coordinations（一组 6 个 default）
  - id: lca-team-pipeline
    name: lca-team-pipeline
    $module: lca.plugins.team.pipeline
  - id: lca-team-fanout
    name: lca-team-fanout
    $module: lca.plugins.team.fanout
  - id: lca-team-graph
    name: lca-team-graph
    $module: lca.plugins.team.graph
  - id: lca-team-debate
    name: lca-team-debate
    $module: lca.plugins.team.debate
  - id: lca-team-peer-relay
    name: lca-team-peer-relay
    $module: lca.plugins.team.peer_relay
  - id: lca-team-peer-swarm
    name: lca-team-peer-swarm
    $module: lca.plugins.team.peer_swarm
  # Middleware / Guard
  - id: lca-guard-loop-intervention
    name: lca-guard-loop-intervention
    $module: lca.plugins.guards.loop_intervention
  - id: lca-guard-step-budget
    name: lca-guard-step-budget
    $module: lca.plugins.guards.step_budget
  # DSH Bridge
  - id: lca-dsh-bridge
    name: lca-dsh-bridge
    $module: lca.plugins.dsh.bridge
  # Gateway
  - id: lca-gateway-starlette
    name: lca-gateway-starlette
    $module: lca.plugins.gateway_starlette
```

**总计**：base.yaml 约 13 Tier-1 + 13 Tier-2 = 26 entries；web-app.yaml 追加 19 Tier-3 = 总 ~45 entries。**L4 组合根不 import 任何具体类**。

```yaml
# Profile 层用 patch 替换 provider：
# profiles/web-standard.yaml
bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml
patch:
  - remove: lca-llm-provider-mock
    insert:
      - id: lca-llm-provider-real
        $module: lca.plugins.providers.llm.real
        inject: ["llm"]
        config:
          api_key: ${LLM_API_KEY}
          base_url: ${LLM_BASE_URL:-https://api.deepseek.com}
```

用户切 real LLM 不用改 Python——改 profile / env。

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

cordis 的 `Context.isolate(label, callback)` 是**回调式**——它不是 async context manager；async context manager 是 `Context.scope(label)`（见 `cordis/context.py:339`）。当前 `composer.py:_isolate_agent_scope` 的语义是构造一个子 scope 并 shadow 服务实例。

```python
# before (composer.py:451-499)
def _isolate_agent_scope(parent: ScopedPluginHost, role: str) -> ScopedPluginHost:
    child = parent.fork(ScopeKind.AGENT, f"agent:{role}")
    spec = PluginSpec(name="compose-shadow", apply=lambda _ctx, _cfg: None)
    handle = PluginHandle(
        entry_id=f"compose-shadow:{child.scope_id}",
        spec=spec,
        config={},
        injected=(),
    )
    child.host.register_handle(handle)
    child.provide(handle, "llm", LlmService())        # line 476
    child.provide(handle, "tools", ToolsService())     # line 477
    child.provide(handle, "transport", TransportService())  # line 478
    mem = MemoryService()
    parent_mem = parent.get("memory")
    if parent_mem is not None:
        for name in parent_mem.providers.names():
            mem.register(name, parent_mem.providers.get(name))
    child.provide(handle, "memory", mem)              # line 485
    stores = StateStoreService()
    parent_stores = parent.get("state_store")
    if parent_stores is not None:
        for name in parent_stores.providers.names():
            stores.register(name, parent_stores.providers.get(name))
    child.provide(handle, "state_store", stores)      # line 492
    return child

# after — async-context-manager (returns child, no yield)
async def _isolate_agent_scope(parent: Context, role: str) -> AsyncContextManager[Context]:
    """Return an async CM that materializes a child scope with shadow services.

    Caller does: ``async with _isolate_agent_scope(parent, role) as child: ...``.
    The returned child gets fresh LlmService / ToolsService / TransportService
    to isolate per-agent provider state; memory / state_store copy parent
    providers into fresh service instances.
    """
    return _IsolatedAgentScope(parent, role)

class _IsolatedAgentScope:
    def __init__(self, parent: Context, role: str) -> None:
        self._parent = parent
        self._role = role
        self._scope_cm = None  # type: AsyncContextManager[Context] | None
        self._child: Context | None = None

    async def __aenter__(self) -> Context:
        self._scope_cm = self._parent.scope(f"agent:{self._role}")
        self._child = await self._scope_cm.__aenter__()
        self._child.provide("llm", LlmService())
        self._child.provide("tools", ToolsService())
        self._child.provide("transport", TransportService())

        # memory / state_store: copy parent providers into fresh instances
        mem = MemoryService()
        parent_mem = self._parent.inject("memory")
        if parent_mem is not None:
            for name in parent_mem.providers.names():
                mem.register(name, parent_mem.providers.get(name))
        self._child.provide("memory", mem)

        stores = StateStoreService()
        parent_stores = self._parent.inject("state_store")
        if parent_stores is not None:
            for name in parent_stores.providers.names():
                stores.register(name, parent_stores.providers.get(name))
        self._child.provide("state_store", stores)
        return self._child

    async def __aexit__(self, *exc_info) -> None:
        if self._scope_cm is not None:
            await self._scope_cm.__aexit__(*exc_info)
```

**重要语义**：cordis 的 `Context.scope(label)` 只是 scope-tracking + 共享 root；它**不**自动 shadow 服务实例。LCA 的 "每 agent 一份独立 LlmService" 的语义需要：
- 显式 `child.provide("llm", LlmService())` 覆盖父
- 由 `async with` 的释放钩子卸载

让 child 保留父的 memory / state_store（providers 列表）需要 `parent.inject("memory").providers` → 拷贝构造新 `MemoryService()`。

**调用点迁移**（`composer.py:226` 调用方）：
```python
# before
compose_scope = _isolate_agent_scope(scope, role)
agent = compose(role, compose_scope, ...)

# after
async with _isolate_agent_scope(scope, role) as compose_scope:
    agent = compose(role, compose_scope, ...)
```

或不返回 CM，只把 child 提为局部变量：
```python
isolator = _IsolatedAgentScope(scope, role)
async with isolator as compose_scope:
    agent = compose(role, compose_scope, ...)
```

### 8.2 `ScopedPluginHost` / `ScopeKind` 的使用点

spec 初稿说"约 6 处 `current_scope()`"——**错的**。`rg "current_scope\("` 返回空。实际引用 `ScopedPluginHost` / `ScopeKind` 接口的位置（`scope.resolve` / `scope.fork` / `scope.provide` / `wrap` / `isinstance`）：

**生产代码**：

| 文件 | 行 | 模式 | 替代 |
|---|---|---|---|
| `lca/layer4_app/composer.py` | 466 | `parent.fork(ScopeKind.AGENT, f"agent:{role}")` | `parent.scope(f"agent:{role}")` |
| `lca/layer4_app/composer.py` | 476–492 | `child.provide(handle, key, value)` | `child.provide(key, value)` |
| `lca/layer4_app/api.py` | 105 | `isinstance(x, ScopedPluginHost)` | `isinstance(x, Context)` |
| `lca/layer4_app/api.py` | (other) | `scope.resolve(...)` | `ctx.inject(...)` |
| `gateway/app.py` | 149–153 | `ScopedPluginHost.wrap(host, ScopeKind.DEPLOYMENT, ...)` | `Context.wrap(host)` + `setup_logging()` |
| `lca/plugins/loop_cognitive.py` | 99, 105 | `plugin_scope.resolve("llm")` / `plugin_scope.resolve("tools")` | `ctx.inject("llm")` / `ctx.inject("tools")` |
| `lca/plugins/loop_dsh_bridge.py` | — | `scope.resolve("session_store")` / `scope.resolve("dsh_settings")` | `ctx.inject(...)` |
| `lca/plugins/loop_replay.py` | — | `scope.resolve("session_store")` | `ctx.inject(...)` |
| `lca/harness/diagnostics/tree.py` | — | tree walker over `ScopedPluginHost` | 重写为 cordis `Context` walker |
| `lca/harness/__init__.py` | 11, 31, 33 | re-exports `ScopedPluginHost` | 删除 |

**测试代码**（P1 同步迁移，否则 kernel 删后跑不通）：

| 文件 | 范围 | 动作 |
|---|---|---|
| `tests/harness/test_phase_a_integration.py` | 25, 28, 93–95, 110, 220, 237, 275, 358 (≈11+ uses) | 改为 `Context` fixture |
| `tests/harness/test_phase_c_factories.py` | fixture + 4 tests | 改为 `Context` fixture |
| `tests/harness/test_phase_d_dsh_bridge.py` | fixture + 2 tests | 改为 `Context` fixture |
| `tests/harness/test_loop_plugin_integration.py` | 10, 29 | 改为 `Context` fixture |
| `tests/harness/test_gateway_profile_integration.py` | 118 | 改为 `Context` fixture |

**注意**：P1 阶段（kernel 删除）必须**同时**改这些测试，否则 `from lca.harness.kernel.scope import ScopedPluginHost` 全部 `ImportError`。

### 8.3 mount / provide 翻译

LCA 在生产代码里有两种 `ctx.mount` 形式：

```python
# before (composer's _isolate_agent_scope, line 476-492)
ctx.mount(handle, "llm", service)              # 3-arg (handle, key, value)
ctx.mount(handle, "llm", service, check=fn)    # 4-arg (with check predicate)

# before (16 plugins' apply() functions, capability_boot.py:38-47)
ctx.mount("llm", service)                      # 2-arg (key, value)

# after — both forms collapse to 2-arg cordis Context.provide
ctx.provide("llm", service)                    # 2-arg (key, value, *, dispose=None)
# check predicate via Service.check classmethod（只在继承 cordis.Service 的类上需要）
```

`handle` 的概念在 cordis 里由 `ctx.fiber.effect` 自动管理——`provide` 不需要显式 handle；插件 setup 里所有写入 `ctx.provide(...)` / `ctx.effect(...)` / `ctx.on(...)` 都是 fiber-owned，卸载时自动撤销。

**注意**：保留 `check` 语义的 LCA capability service 会落到 `cordis.Service` 子类，否则默认 `service.check()` 返回 True。LCA 当前的 11 个 capability service 都很简单，不需要 `check` 谓词。

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
| **P5** | 21 个 Tier-1 plugin 改写为 `@plugin` 形式（module-per-plugin：每个 plugin file ≤ 50 行；service 类搬回 `lca/layer0_infra/capability/` 或 layer2/3 归口模块） | `uv run pytest lca/plugins/ tests/test_plugin_*.py` |
| **P5.1** | Tier-2 Provider plugins 抽出（30+ entry：每个 capability seam 至少 1 个 default provider；`lca/layer4_app/capability_boot.py` 删除） | `uv run pytest tests/test_provider_*.py` + `lca/lca-ops status` 不再有 `capability_boot` 警告 |
| **P5.2** | Tier-3 Behavior plugins 抽出（15+ entry：brain / reasoner / synthesizer / team coordination / middleware / dsh bridge） | `uv run pytest tests/test_compose_*.py tests/test_team_*.py` |
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
| `PluginConfig` 保留，但 `plugin.py` 拆分后忘记 re-export | 中 | 阻塞 | P2 阶段 `from lca.contracts.mechanisms.plugin import PluginConfig` 跑通；剩余 2 个 surviving consumer（`tests/test_plugin_loader.py` + `tests/plugin/test_contracts.py`）P1 + P5 同步迁移 |
| `lca/harness/middleware/registry.py` 拆 `COGNITIVE_POINTS` 时漏掉中间件 plugin 引用 | 中 | 阻塞 | P3 阶段先 `rg COGNITIVE_POINTS` 找全 |
| `_isolate_agent_scope` 改写后 `Context.scope(label)` 不创建新 `LlmService` 实例 | 高 | 行为破坏 | 显式 `child.provide("llm", LlmService())` 覆盖父；`tests/test_compose_*.py` 用两个并发 agent 验证（不能互相覆盖） |
| `bundles/base-spine.yaml` → `bundles/base.yaml` 改名打破外部引用 | 低 | 持续集成 | P6 阶段 `rg "base-spine"` 全仓扫（已知引用：`profiles/web-standard.yaml`、`tests/test_phase_a_integration.py`、`docs/superpowers/specs/2026-08-16-plugin-tree-runtime-design.md`、`lca-ops` 脚本） |
| `loop_dsh_bridge` 内部 plugin scope resolve 改写时回归到旧 `lca.harness.kernel` 路径 | 中 | 阻塞 | P7 阶段把 dsh_bridge 放进 `tests/test_loop_dsh_bridge.py` 隔离测试 |
| `lca_harness.profile.boot()` 公开 API 仍被外部脚本调用 | 低 | 阻塞 | P4 阶段保留 `boot_profile(path, *, check_seam_completeness)` 签名（`check_seam_completeness` 变为 no-op 警告）；`gateway/app.py:138` 和 `tests/harness/test_phase_a_integration.py:225` 跑通 |
| `PluginContext` Protocol 在 P5 后变孤儿（2 个使用 plugin `budget_policy`/`loop_intervention_policy` 改写后无 caller） | 低 | 死代码 | P5 完成后删除 `lca/contracts/harness/plugin.py:PluginContext` 定义；保留 `lca/contracts/harness/plugin.py` 文件作为 LCA harness 抽象的归口（仅留 `PluginContext` 一个 type alias） |
| vendor 同步：taiyi 未来更新 cordis 时 LCA 同步 | 低 | 长期 | 写 `scripts/sync_vendor.sh` 借鉴 taiyi 同步协议 |
| `Hook` 名字冲突（cordis 导出 `Hook` class；LCA `lca/contracts/mechanisms/__init__.py` 也有 `Hook` Protocol） | 低 | 命名冲突 | 所有 LCA 内部继续 `from lca.contracts.mechanisms import Hook`；不 re-export cordis 符号；如要交叉 import 显式 `from cordis import Hook as CordisHook` |
| `seam_key` 命名不一致：COGNITIVE_POINTS[0] 是 `agent.pre_step`；`budget_policy` plugin 引用 `agent.before_step`；其他 9 个名称一致 | 低 | 命名漂移 | P3 阶段统一为 `agent.before_step` / `agent.after_step` 风格；全仓 `rg "agent\.(pre|before)_step"` 找全 |

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
