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
- 删 `lca/contracts/harness/plugin.py` + `lca/contracts/mechanisms/plugin.py` + `lca/contracts/mechanisms/seam.py`
- 21 个 `lca/plugins/*` 改写为 `@plugin` 形式
- `bundles/base-spine.yaml` + `profiles/web-standard.yaml` 改为 cordis YAML
- `lca/layer4_app/composer.py:_isolate_agent_scope` 用 cordis Context 改写
- vendor 引入 `taiyi-cordis` / `taiyi-cosmokit` / `taiyi-schemastery`

**Out**:
- 不 port dsh 100+ 包（subagent / sandbox / LSP / MCP / ACP / compaction / skill / goal / workflow / jobs / todo / plan / preset / guard / hooks / session-query / settings / credentials / attachment / fs / lsp / terminal / code-runtime / shell / subprocess / e2b / feedback / context / identity / interaction / web / storage / workspace / boot / sdk / examples / support / util / typert）
- 不重写 `lca/contracts/protocols/` 的 22 个 Protocol
- 不动 LCA 5 层单向依赖 import 图
- 不动 `lca/contracts/{atoms,models}/` 纯数据契约
- 不改 Journal 真相机制（ADR-0037）
- 不改 L4 组合根 API（`Agent` / `Team` / `TeamLead`）

---

## 2. 第一性原理

1. **vendor 唯一 = cordis**。DSH 的 cordis 是经过产品考验的运行时；taiyi 的 1:1 Python 移植可用。LCA 自家复刻只是临时脚手架，留下来就是双轨约定。
2. **协议是架构的硬骨；runtime 是方法的肉**。`lca/contracts/protocols/` 的 22 个 `@runtime_checkable Protocol` 是真抽象，价值高于 runtime——保留。`lca/contracts/harness/plugin.py` 的 `Manifest`/`ExtensionPoint`/`CapabilityGrant` 在 dsh 都没对应物，是 LCA 早期自创的中间层，删。
3. **plugin = 行为单位**。21 个 capability 插件都是有用的；plugin 集不缩——只在文件夹 + 命名上重新组织。
4. **scope 在 cordis 上重新表达**。LCA 自创的 5-ScopeKind 是语义名词（DEPLOYMENT/PROFILE/TEAM/AGENT/SESSION），cordis 的 `Context.isolate` / `Context.fork` 不需要语义枚举——`"agent:{role}"` 这种 label 字符串足够。把 ScopedPluginHost 从一个类简化成一个 `async with ctx.isolate(label)`。
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
# lca/plugins/llm_service/__init__.py
from __future__ import annotations
from cordis import plugin, Service
from pydantic import BaseModel

class Config(BaseModel):
    model_config = {"extra": "forbid"}
    default_provider: str = "mock"

class LlmService(Service):
    """Service Definition for the LLM seam. Owns the provider registry."""
    def __init__(self, ctx, **config):
        super().__init__(ctx)
        self._providers: dict[str, object] = {}
        self._default = config.get("default_provider", "mock")

    def register(self, name: str, adapter, *, activate: bool = False) -> None:
        self._providers[name] = adapter
        if activate and not self._default:
            self._default = name

    async def complete(self, *args, **kwargs):
        return await self._providers[self._default].complete(*args, **kwargs)

@plugin(name="lca-llm-service", inject=())
async def setup(ctx, config: Config):
    service = LlmService(ctx, **(config.model_dump() if config else {}))
    ctx.provide("llm", service)
```

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
| `lca/harness/kernel/` | 删除 | cordis 替代 |
| `lca/harness/profile/boot.py` | 重写为 cordis 包装 | 公开 API 保留 |
| `lca/contracts/harness/plugin.py` | 删除 | cordis 替代 |
| `lca/contracts/mechanisms/plugin.py` | 删除 | cordis 替代 |
| `lca/contracts/mechanisms/seam.py` | 删除 | dsh 不用 seam 三角色 |
| `lca/plugins/seam_definitions/` | 删除 | cordis 不需要 |

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

原 `agent_service` 是 `session.append` 的 typed facade：

```python
# before
await agent_service.record_assistant_response(store, turn, step, content, ...)

# after
await session_service.record_assistant_message(session_id, turn, step, content, ...)
```

`SessionService` 加一组 `record_*` 方法（`record_user_message` / `record_assistant_message` / `record_tool_call` / `record_tool_result` / `record_turn_start` / `record_step_start` / ...）；调用方路径从 `agent_service.record_*` → `session_service.record_*`。

---

## 7. bundle / profile 改写

### 7.1 `bundles/base.yaml`（替代 `base-spine.yaml`）

cordis 的 bundle 是 entry 列表：

```yaml
# bundles/base.yaml
plugins:
  - name: lca-llm-service
    $module: lca.plugins.llm
  - name: lca-llm-provider
    $module: lca.plugins.llm.provider
    inject: ["llm"]
    config:
      mode: auto
  - name: lca-tools-service
    $module: lca.plugins.tools
  - name: lca-session-service
    $module: lca.plugins.session
  - name: lca-system-prompt-service
    $module: lca.plugins.system_prompt
  - name: lca-transport-service
    $module: lca.plugins.transport
  - name: lca-skills-service
    $module: lca.plugins.skills
  - name: lca-file-store-service
    $module: lca.plugins.file_store
  - name: lca-observability-service
    $module: lca.plugins.observability
  - name: lca-sandbox-service
    $module: lca.plugins.sandbox
  - name: lca-memory-service
    $module: lca.plugins.memory
  - name: lca-search-service
    $module: lca.plugins.search
  - name: lca-state-store-service
    $module: lca.plugins.state_store
```

### 7.2 `bundles/web-app.yaml`

```yaml
plugins:
  - $patch: bundles/base.yaml
  - name: lca-loop-cognitive
    $module: lca.plugins.agent_loop.cognitive
  - name: lca-gateway-starlette
    $module: lca.plugins.gateways.starlette
  - name: lca-guard-loop-intervention
    $module: lca.plugins.guards.loop_intervention
  - name: lca-guard-step-budget
    $module: lca.plugins.guards.step_budget
```

### 7.3 `profiles/web-standard.yaml` 改写

```yaml
bundles:
  - bundles/web-app.yaml
patch: []
```

---

## 8. `lca/layer4_app/composer.py` 重写

### 8.1 `_isolate_agent_scope` 改动

```python
# before
def _isolate_agent_scope(parent: ScopedPluginHost, role: str) -> ScopedPluginHost:
    child = parent.fork(ScopeKind.AGENT, f"agent:{role}")
    child.provide(handle, "llm", LlmService())  # 三参数
    ...

# after
async def _isolate_agent_scope(parent: Context, role: str) -> Context:
    async with parent.isolate(f"agent:{role}") as child:
        child.provide("llm", LlmService())  # 二参数
        child.provide("tools", ToolsService())
        child.provide("transport", TransportService())
        # memory / state_store 沿用父（深拷贝 providers）
        ...
        yield child
```

### 8.2 `current_scope()` 替代

LCA 中所有 `current_scope()` 调用点（约 6 处）：`diag.tree` / `loop_replay` / `composer` / `api`。

```python
# before
scope = current_scope()

# after
scope = Context.current()  # cordis 自带
```

### 8.3 mount / provide 翻译

```python
# before
child.provide(handle, "llm", service)            # 三参数 (handle, key, value)
child.provide(handle, "llm", service, check=fn)  # 四参数

# after
child.provide("llm", service)                    # 二参数 (key, value)
# check predicate via Service.check classmethod
```

`handle` 的概念在 cordis 里由 `ctx.fiber.effect` 自动管理——`provide` 不需要显式 handle；插件 setup 里所有写入 `ctx.provide(...)` / `ctx.effect(...)` / `ctx.on(...)` 都是 fiber-owned，卸载时自动撤销。

---

## 9. 迁移序列

| Phase | 内容 | 验证 |
|---|---|---|
| **P0** | vendor 引入 cordis + cosmokit + schemastery（`uv sync` 跑通） | `uv run python -c "from cordis import Context, plugin, Service"` |
| **P1** | 删 `lca/layer0_infra/plugin/` + `lca/harness/kernel/` + `lca/harness/profile/boot.py` | `rg -l lca.layer0_infra.plugin` 空 |
| **P2** | 删 `lca/contracts/{harness/plugin.py, mechanisms/plugin.py, mechanisms/seam.py}` | `rg -l "PluginManifest\|ExtensionPoint\|CapabilityGrant"` 仅命中 docstring |
| **P3** | `lca/harness/profile/boot.py` 重写为 cordis.Loader 薄包装 | `lca-ops status` 跑通 |
| **P4** | 21 个 plugin 改写为 `@plugin` 形式（一次提交） | `uv run pytest lca/plugins/ tests/test_plugin_*.py` |
| **P5** | bundle / profile YAML 改写 | `lca-ops status` + `lca-ops inspect-tree` |
| **P6** | `composer.py` + 6 个 `current_scope()` 调用点改写 | `uv run pytest lca/layer4_app/` + `examples/pluggability_demo/` |
| **P7** | 端到端：`scripts/run_team_mode.py` 跑通真 e2e | Agent reply 在 journal |
| **P8** | `loop_dsh_bridge` 重新挂上（之前在 P4 跑过 stub） | `lca-ops logs` 看 dsh bridge 记录 |

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
| `composer.py` 多处 `ScopedPluginHost` 引用漏改 | 中 | 阻塞 | `rg -l ScopedPluginHost\|current_scope` 找出 6 个点逐个改 |
| cordis 的 `@plugin` + Standard Schema 校验在 extra="forbid" 上某些 capability 需要 `model_config` 调整 | 低 | 测试挂 | P4 阶段单 plugin 跑 mypy |
| `bundles/base-spine.yaml` → `bundles/base.yaml` 改名打破外部引用 | 低 | 持续集成 | `rg "base-spine" ` 全仓扫 |
| `lca/plugins/seam_definitions` 有测试依赖 | 中 | 阻塞 | P2 阶段先 `rg seam_definitions` |
| `loop_dsh_bridge` 内部还要 `lca.harness.kernel` 某个工具 | 中 | 阻塞 | cordis 替代后 dsh_bridge 也要改写 |
| `lca_harness.profile.boot()` 公开 API 仍被外部脚本调用 | 低 | 阻塞 | 保留 `boot_profile()` function 名字，内部改实现 |
| vendor 同步：taiyi 未来更新 cordis 时 LCA 同步 | 低 | 长期 | 写 `scripts/sync_vendor.sh` 借鉴 taiyi 同步协议 |

---

## 12. 不在范围（明确 YAGNI）

- 100+ dsh 包的 Python port（subagent / sandbox / LSP / MCP / ACP / compaction / skill / goal / workflow / jobs / todo / plan / preset / guard / hooks / session-query / settings / credentials / attachment / fs / lsp / terminal / code-runtime / shell / subprocess / e2b / feedback / context / identity / interaction / web / storage / workspace / boot / sdk / examples / support / util / typert）
- 不动 `lca/contracts/protocols/` 的 22 个 `@runtime_checkable Protocol`
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
- `rg -l ScopedPluginHost\|PluginManifest\|ExtensionPoint` 仅命中 docstring
- `uv run vulture lca --min-confidence 80` 干净
