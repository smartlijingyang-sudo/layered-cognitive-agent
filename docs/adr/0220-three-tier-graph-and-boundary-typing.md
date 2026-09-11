# ADR-0220: 三层图概念群与 boundary typed DTO — `PromptReasoner` 减肥,`AgentState` 不持 ref,图与图用 boundary 互通

> **状态:** **Proposed — 2026-09-11**
>
> **一句话**: 把当前"图 = 代码分组"重构成"图 = 概念群"。把 LCA 图家族分为三层:**Layer 1 原语图** (`primitive.*`, 运行时原语) / **Layer 2 概念图** (`concept.*`, 可复用领域概念) / **Layer 3 业务图** (`business.*`, profile-specific 业务编排);每张图只做一件事,跨图通过 11 个 **boundary typed DTO** (`BindingsView` / `ForkedTools` / `RoleSnapshot` / `ReasonerContext` / `TemplateSelection` / `ReasonerTurnRender` / `Decision` / `EffectReceipt` / `Reflection` / `MemoryReceipt` / `StopPayload`) 显式互通。`PromptReasoner` 从 7 方法缩到 2 方法 (`render_turn` / `complete_turn`),`AgentState` 删除 `_file_store_ref` / `_sandbox_ref` / `_skill_store_ref` / `_machine_resolver_ref` / `_search_ref` 私有属性,seam 全部走 `RuntimePlane`;`reasoner_provider.setup` 的 `runtime().inject("tools")` 偷 inject 路径彻底删除。
>
> **触发**: 在 ADR-0217/0218/0219 落地后,`run_5b8c2a9f1e70` (`objective=ping`, H6) 虽 broken_hop=None,但 `PromptReasoner._resolve_tools` (reasoner.py:285-313) 仍反射读 6 个 state 私有属性,`PromptReasoner._legacy_*` (reasoner.py:472-533) 三个 legacy 方法 + `_legacy_templates` 私有 dict 仍持有;`reasoner_provider.setup` (reasoner_provider.py:113-126) 仍走 `runtime().inject("tools")` 偷 inject,绕过 Cordis manifest `requires=`。同一根因引发的现象链:
>
> 1. `think.reason.complete` 节点调 `PromptReasoner.complete_turn`,第一行 `self._resolve_tools(state)` 反射读 `state._file_store_ref` / `_sandbox_ref` / `_skill_store_ref` / `_machine_resolver_ref` / `_search_ref` / `state.bindings` — 6 个属性,任何一个 `None` 都 silently 退回 boot-time `self.tools`
> 2. `ToolsService.fork_for_run(run_bindings)` 内部又把 run_bindings 6 个 ref 反射塞进每个 `ToolFactory.bind()`,工厂签名不对就 `TypeError` 被 `except Exception` 吞掉
> 3. `PromptReasoner.build_turn_plan` 调 `self._select_template` → `_legacy_select_template` (回退到 `react_prompt` / `routing_prompt` / `hierarchical_prompt` 字面) 而不是 `PromptTemplateSelector.select` —— legacy fallback 是 dead path,生产里 `PromptTemplateSelector` 必装,但 fallback 还在,新人改代码不知道
> 4. `reasoner_provider.setup` 用 `runtime().inject("tools")` 绕过 `requires=` 校验,声明与实际不一致 — 这是 ADR-0219 §0.3 "同一根因第二次出现 = 上次没修对" 的另一种形式 (上一次是 interpreter 偷 phase 名,这次是 setup 偷 capability)
>
> 但根因不止 seam 偷取和 legacy 死代码。**真正的根因是图被当成代码分组,不是概念分组**。`think.yaml` 5 个节点 (`think.shortcut` / `think.route` / `think.reason` / `think.classify` / `think.gate`) 全部带 `think` 前缀,但 `think.reason` 节点同时承担模板选择 + prompt 渲染 + LLM 调用 + tools 反射拼装 + ContextVar 绑定 + legacy fallback —— **节点名字和职责不对应**;`bundles/declarative-phase-graph.yaml` 把 6 个 phase 写成 6 行 topology 配置,但 perceive / prep / reflect / remember / stop 这些 phase 在代码里就是 6 个 plugin,profile 改 phase 顺序要重写 plugin,改业务不改图。
>
> **Agent Note** (实施时): `docs/notes/implemented/seam/2026-09-11-three-tier-graph-and-boundary.md` (P1—P10 同步收口,见 §11)
>
> **Review:** 待评审
>
> **Accepted 闸门:**
>
> 1. §3 三层图 schema (`primitive.*` / `concept.*` / `business.*`) 在 `bundles/` 下建立独立目录,`./scripts/lca-ops audit-plugin-shape` 把图层作为 `PluginKind` 一等公民登记
> 2. §4 11 个 boundary typed DTO (`BindingsView` / `ForkedTools` / `RoleSnapshot` / `ReasonerContext` / `TemplateSelection` / `ReasonerTurnRender` / `Decision` / `EffectReceipt` / `Reflection` / `MemoryReceipt` / `StopPayload`) 在 `lca/contracts/models/cognition/boundary.py` 集中定义,全部 `model_config = ConfigDict(extra="forbid", frozen=True)` (`ReasonerBundle` 是 `business.reasoning.turn` 内部 4 DTO 聚合, 不算 boundary, 见 §5)
> 3. §5 `business.reasoning.turn` 是 `bundles/business/reasoning_turn.yaml` 存在并通过 `tests/integration/think/test_business_reasoning_turn.py::test_e2e_with_prep_graph`
> 4. §6 `PromptReasoner` 类只剩 `render_turn` / `complete_turn` 两个方法;`_tools_service` / `_resolve_tools` / `_legacy_select_template` / `_legacy_variables` / `_legacy_templates` 五个私有成员删除;`cognition/brain/reasoner/reasoner.py` ≤ 280 行 (当前 544 行)
> 5. §7 `AgentState` 删除 `_file_store_ref` / `_sandbox_ref` / `_skill_store_ref` / `_machine_resolver_ref` / `_search_ref` 5 个私有属性;`reasoner.py` 中 `getattr(state, "_xxx_ref", None)` 调用全部归零
> 6. §8 `reasoner_provider.setup` 删除 `runtime().inject("tools")` 偷 inject 路径;`bundles/base.yaml` 增加 `phase.think.reasoner.credentials` 和 `phase.think.reasoner.compose` 两个 plugin id,manifest 显式声明 `requires=("tools",)`
> 7. §9 端到端:`./scripts/lca-ops runs create --user-text "ping" --wait --json` 跑通六语义 `perceive → think → act → reflect → remember → stop`,`broken_hop=None`;新路径走 `business.run.phase` 单业务图
> 8. §10 既有测试全过:`tests/think/` + `tests/integration/think/` + `tests/harness/graph/execute/` 共 100+ 不退化;新增 `tests/business/test_three_tier_graph_dispatch.py` 验证原语图 / 概念图 / 业务图三层拓扑不交叉
> 9. §11 零 `grep -rn "getattr(state, \"_\(file_store\|sandbox\|skill_store\|machine_resolver\|search\)_ref\"" lca/` = 0;零 `grep -rn "runtime().inject(" lca/plugins/` = 0;零 `grep -rn "self\._legacy_\(select_template\|variables\|templates\)" lca/` = 0

**编号:** 0220

**关系:**
- **Builds on**: ADR-0217 (Bundle Graph Schema v2 — 我们用它写更多图) · ADR-0218 (subgraph driver — `subgraph_ref:` 用于业务图嵌入子图) · ADR-0219 (phase-graph unification — 我们强化其 N1 / N5) · ADR-0075 (6 phase 仍 6 phase, phase 现在是 "业务图" 而非 "plugin") · ADR-0035 (Solo/Member/Lead Reasoner — 这层 Profile 选择,不是图结构) · ADR-0074 (Control plane — control plugins 仍存在,挂在图节点的 control slot) · ADR-0156 (eliminate projection leakage — boundary DTO 是 typed projection,不泄漏到 state)
- **Refines**: `PromptReasoner` (从 7 方法缩到 2) · `AgentState` (从隐式 seam 容器退到纯业务状态) · `ToolsService.fork_for_run` (从反射 6 个 ref 改 typed binding_keys) · `reasoner_provider.setup` (从偷 inject 改显式 requires)
- **Supersedes**: 无
- **Extends**: ADR-0219 §0.4 N1—N6 (新增 N7—N10,见 §0.4)
- **Reject**: 「把 `PromptReasoner` 直接拆成 3 个 plugin (`build_turn_plan_provider` / `render_turn_provider` / `complete_turn_provider`)」(违反职责清晰 — 三个方法共享同一份 `assembler` / `selector` / `role_profile`,各自 plugin 会重复持有,seam 反而裂开);「把 `prep` 做成 think 子图的前置节点而不是独立图」(隐式把 "准备" 塞进 think,违反 G1 一张图 = 一个职责, perceive → think 之间没有显式 boundary);「只删 `_resolve_tools` 但保留 `_legacy_*` fallback」(违反 C6 最小化, fallback 是 dead path, 删除才彻底);「保留 `state._xxx_ref` 但让 `PromptReasoner` 不反射读」(违反 boundary discipline, state 仍是隐式 seam 容器, 下次还会有人反射读)

---

## 0. 第一性原理: 问题本质

### 0.1 图的本质 vs 当前实现

图应当是**领域概念的容器**,不是**代码函数的容器**。当前 LCA 把图当成 yaml 化的 "if-else 链",节点是代码函数,边是控制流。这导致两个症状:

1. **节点名字和职责不对应** — `think.reason.plan` 这个名字说 "做 plan",但节点同时在做模板选择 (`_legacy_select_template`) + role snapshot (`_legacy_variables`) + prompt 渲染 (`_render_prompt`);读者按名字去找实现,找不到
2. **图没有复用价值** — `think.reason.complete` 调一次 LLM, 但 `concept.reflection.critique` 也调 LLM, 两处复制 `_bind_reasoner_prompt` + `_step_id_for_trace` + ModelVisible ContextVar 绑定逻辑;想复用就要把 LLM 调用抽出来,但当前结构里 LLM 调用是 `_complete_turn` 的私有方法

**重新设计的目标**: 图 = **纯变换的拓扑**, 节点 = **可独立测试的最小语义动作**, 边 = **typed DTO 流**, 跨图 = **命名 boundary**。读图 (yaml) 就知道系统在做什么。

### 0.2 当前 4 个 seam 的异味溯源

| seam | 异味 | 根因 |
|---|---|---|
| `PromptReasoner` (reasoner.py:144-543) | 7 个方法 (`__init__` / `register_template` / `build_turn_plan` / `render_turn` / `complete_turn` / `generate_thoughts` / `_resolve_tools` / `_legacy_select_template` / `_legacy_variables`) + 5 个私有成员 (`_tools_service` / `_legacy_templates` / `tools` / `catalog` / `assembler`) | 类是 "图伪装" — 一个类装了一整条数据流,每 turn 还要自己反射拼装 per-run 上下文 |
| `AgentState._xxx_ref` 系列 (5 个 `_xxx_ref` 私有属性) | state 不是纯业务状态, 而是隐式 seam 容器;`reasoner.py:300-305` 用 `getattr(state, "_file_store_ref", None)` 反射读 | 状态对象和 capability seam 边界失守, 下次还会有人反射读别的 ref |
| `ToolsService.fork_for_run` (tools.py:73-89) | 接 `run: Any` 透传给 `factory(run)`, 每个 `ToolFactory.bind(run)` 自己反射读 6 个属性 | fork 接口不 typed, factory 签名靠鸭子类型, 改一个 ref 就 break 一片 |
| `reasoner_provider.setup` (reasoner_provider.py:113-126) | `runtime = getattr(ctx, "_runtime", None)` 偷 cordis 私有 API, `runtime().inject("tools")` 绕过 manifest `requires=` 校验 | 声明与实际不一致 — manifest 说 `requires=("reasoner.role_profile",)`, 实际还偷 `tools` capability |

### 0.3 为什么 "只删 `_resolve_tools` 不行"

按 AGENTS.md §1.5 §2 "**同一根因第二次出现 = 上次没修对**":

- ADR-0219 (本次) 修了 interpreter 偷 phase 名, 但 `reasoner_provider.setup` 偷 capability 是同一类违例 (绕过 manifest) —— 上次没修 seam 偷取这条根因
- `PromptReasoner._resolve_tools` 反射读 state 是 "seam 跨边界走 duck-type" 的另一种形式 — 上次修了 interpreter 业务名, 没修这里 duck-type 反射
- `PromptReasoner._legacy_*` 三个 fallback 是 "dead path 没清掉" 的另一种形式 — 上一波收尾了 `ModularBrain` legacy, 但 `PromptReasoner` legacy 还留着, 因为 "删了怕 break 测试"
- 不修图分层: `concept.reflection.critique` 和 `think.reason.complete` 还是会复制 LLM 调用逻辑
- 不修 boundary 命名: 跨图传输用裸 DTO 还是裸 dict, 不知道哪里是 boundary
- 不修 state 反射: 下次加新的 per-run ref (比如 `_event_bus_ref`), 又会有人 `getattr(state, "_event_bus_ref", None)`

### 0.4 不变量 (本 ADR 之后, 接续 ADR-0219 §0.4 N1—N6)

| ID | 不变量 | 验证手段 |
|---|---|---|
| **N7** | 图分三层: `primitive.*` / `concept.*` / `business.*`; 任何图 bundle 路径必须匹配其中一个前缀 | `ls bundles/primitive*/ bundles/concept*/ bundles/business/` 各自存在; `find bundles -name "*.yaml" | grep -v "^bundles/\\(primitive\\|concept\\|business\\)/"` 第三方图只能放在子目录, 不允许顶级有图 |
| **N8** | boundary typed DTO 在 `contracts/models/cognition/boundary.py` 集中定义; 跨图输入输出必须走 boundary DTO, 不允许裸 `dict` / `Mapping` | `grep -rn "dict\\[str, Any\\]" lca/contracts/models/cognition/boundary.py` = 0; 全部 DTO `frozen=True` + `extra="forbid"` |
| **N9** | 节点 id 命名: `<动作域>.<对象>.<细节>`, 第一层动作域在闭集内 (`tool.*` / `prompt.*` / `decision.*` / `gate.*` / `effect.*` / `context.*` / `skill.*` / `memory.*` / `state.*` / `observe.*` / `spine.*` / `capability.*` / `llm.*` / `shortcut.*` / `perceive.*` / `reflect.*` / `stop.*`); 禁词 `process` / `handle` / `manage` / `do_*` / `xxx_impl` / `xxx_helper` | `scripts/lca-ops audit-bundle-node-naming` 新增 (本 PR 加) |
| **N10** | `PromptReasoner` 类只剩 `render_turn` / `complete_turn` 两个公开方法; 私有成员只允许 `llm` / `role_profile` / `assembler` / `selector` (4 个 boot-time singleton ref); 其他私有成员 (`_tools_service` / `_legacy_templates` / `_available_skills` / `tools` / `_resolve_tools` / `_select_template` / `_legacy_select_template` / `_legacy_variables` / `_template_section_names` / `_template_variant` / `_bind_reasoner_prompt` / `_reset_reasoner_prompt` / `_step_id_for_trace` / `_available_skills_count_hint` / `_legacy_variables` / `register_template` / `build_turn_plan` / `generate_thoughts`) 全部删除 | `reasoner.py` ≤ 280 行; `grep -n "def " lca/cognition/brain/reasoner/reasoner.py` = 4 (构造函数 + 2 公开 + 1 dunder) |
| (接 N1) | interpreter 不持有任何 `SemanticPhase` 字面 | (见 ADR-0219 §0.4) |
| (接 N5) | `node_graph_driver.py` 不调 outer interpreter API | (见 ADR-0219 §0.4) |

---

## 1. 设计原则

| 原则 | 本 ADR 怎么落 |
|---|---|
| 第一性原理 | 图是纯变换拓扑, 节点是最小语义动作, 边是 typed DTO 流 — 重画图就是重画认知 |
| 职责单一 | 三层图各做各的: 原语图做运行时原语, 概念图做领域概念, 业务图做业务编排; 一张图一个职责 |
| 模块化 | 节点不持上下文; capability 走 RuntimePlane, 不走 state 私有属性; business 图只引用 concept/primitive 图, 不写节点 |
| 边界清晰 | 11 个 boundary typed DTO (`BindingsView` / `ForkedTools` / `RoleSnapshot` / `ReasonerContext` / `TemplateSelection` / `ReasonerTurnRender` / `Decision` / `EffectReceipt` / `Reflection` / `MemoryReceipt` / `StopPayload`) 是跨图唯一通道; boundary 有名字有类型, 不裸 dict (`ReasonerBundle` 是 `business.reasoning.turn` 内部聚合, 不算 boundary) |
| 优雅 | typed 闭集替字符串字面 (`tool.fork.dispatch` 替代 `process_tool_fork`); 每个 boundary DTO 都有 D1/D2/D3/D4 四问 |
| 不留临时代码 | 不引入 compat shim; 同 PR 删除 `_resolve_tools` / `_legacy_*` / `_tools_service` / `state._xxx_ref` / `runtime().inject("tools")` / `_strip_think_reason_complete` / `cognitive_emit.run_reasoner_generate_thoughts_with_spine_facts` duck-type 路径 |
| 测试是设计的一部分 | 每张图必须有 e2e 测试; boundary DTO 必有 frozen + extra=forbid 契约测试 |

---

## 2. 现状 (必读的 4 个 seam)

### 2.1 `PromptReasoner` 的 7 个方法 + 5 个私有成员 (异味点 1)

```python
# lca/cognition/brain/reasoner/reasoner.py:144-543
class PromptReasoner:
    def __init__(self, llm, role_profile, ...): ...        # 方法 1
    def register_template(self, name, template): ...         # 方法 2 (legacy)
    def build_turn_plan(self, state): ...                   # 方法 3 → 移到 concept.template.sel + reason.prepare.template
    def render_turn(self, state, plan): ...                 # 方法 4 → 保留 (concept.prompt.render)
    async def complete_turn(self, state, render): ...        # 方法 5 → 保留 (primitive.llm.call)
    async def generate_thoughts(self, state): ...           # 方法 6 → 删除 (业务图自己组合 plan/render/complete)
    def _resolve_tools(self, state): ...                    # 方法 7 → 删除 (走 boundary ForkedTools)

    # 5 个私有成员
    self.llm = adapter                                       # 保留 (boot singleton)
    self.role_profile = role_profile                         # 保留 (boot singleton)
    self.assembler = assembler                               # 保留 (boot singleton)
    self.selector = selector                                 # 保留 (boot singleton)
    self.tools_desc / self.catalog / self.tools = ...        # 删除 (per-run projection, 走 ForkedTools)
    self._legacy_templates = dict(templates or {})          # 删除 (legacy dead path)
    self.available_skills = available_skills                 # 删除 (per-run projection, 走 ReasonerContext)
    self._tools_service: object | None = None                # 删除 (seam 偷取, 走 explicit require)
```

**职责重分配**:
- `render_turn` → `concept.prompt.render` 图节点 (吃 `ReasonerContext` + `TemplateSelection` + `RoleSnapshot`, 出 `ReasonerTurnRender`)
- `complete_turn` → `primitive.llm.call` 图节点 (吃 `ReasonerTurnRender.prompt` + `ForkedTools`, 出 `LLMResponse` + spine EP)
- `build_turn_plan` 拆分 → `concept.template.select` (template 选择) + `concept.context.compose` (context 组合) + `concept.role.snapshot` (role 冻结), 三个独立概念图
- `_resolve_tools` 删除 → `concept.tool.fork` 图节点 (吃 `ToolsService` capability ref + `BindingsView`, 出 `ForkedTools` typed)
- `_legacy_*` 全部删除 → 是 dead path, 保留违反 C6 最小化

### 2.2 `AgentState._xxx_ref` 私有属性 (异味点 2)

```python
# lca/contracts/models/core/state/state.py  (推测位置, 实际需 audit)
class AgentState(BaseModel):
    ...
    # 5 个 seam 容器私有属性 — 全部删除
    _file_store_ref: FileStore | None = None
    _sandbox_ref: Sandbox | None = None
    _skill_store_ref: SkillStore | None = None
    _machine_resolver_ref: MachineResolver | None = None
    _search_ref: SearchService | None = None
    bindings: Bindings | None = None  # 公开, 走 BindingsView

# 反射消费方 (reasoner.py:300-305) — 全部删除
run_binding = {
    "file_store": getattr(state, "_file_store_ref", None),
    "bindings": getattr(state, "bindings", None),
    "sandbox": getattr(state, "_sandbox_ref", None),
    "search": getattr(state, "_search_ref", None),
    "skill_store": getattr(state, "_skill_store_ref", None),
    "machine_resolver": getattr(state, "_machine_resolver_ref", None),
}
```

**正确路径**: `BindingsView` 是 boot-time 由 `RuntimePlane` 暴露的 per-run bindings 视图, `ToolsService.fork_for_run(bindings_view)` 接 typed `BindingsView` 不接 `Any`。`AgentState` 只携带业务数据 (`step` / `task` / `team_awareness` / `activated_skills` / `decision` / ...), 不携带 capability ref。

### 2.3 `ToolsService.fork_for_run` 接 `run: Any` (异味点 3)

```python
# lca/infrastructure/capability/tools/tools.py:73-89
def fork_for_run(self, run: Any) -> ToolsService:
    forked = ToolsService()
    for name, factory in self._factories.items():
        bound = factory(run)  # duck-type, 不知道 factory 要什么
        ...
```

**正确路径**: `fork_for_run(bindings: BindingsView)` 接 typed `BindingsView`; `BindingsView` 显式列出 `file_store` / `sandbox` / `skill_store` / `machine_resolver` / `search` / `bindings` 6 个 capability ref; factory 签名 `bind(bindings: BindingsView) -> Tool | None` typed; 反射归零。

### 2.4 `reasoner_provider.setup` 偷 inject (异味点 4)

```python
# lca/plugins/think/reasoner_provider.py:113-126
runtime = getattr(ctx, "_runtime", None)
if callable(runtime):
    try:
        tools_service = runtime().inject("tools")  # 偷 cordis 私有 API
    except Exception:
        tools_service = None
reasoner = PromptReasoner(llm=adapter, role_profile=role_profile)
reasoner._tools_service = tools_service  # type: ignore[attr-defined]  # 挂私有属性
ctx.provide("reasoner", reasoner)
```

**正确路径**: 拆为两个 plugin:
- `phase.think.reasoner.credentials` — `requires=()`, `provides=("llm_adapter",)`; 读 env + `ProductionLLMResolver.resolve()` → `LLMAdapter`
- `phase.think.reasoner.compose` — `requires=("llm_adapter", REASONER_ROLE_PROFILE.key, "tools")`, `provides=("reasoner",)`; 构造 `PromptReasoner(llm=adapter, role_profile=role_profile, assembler=...)`, `tools` 走 manifest 校验, 不偷 inject

---

## 3. 三层图 schema

### 3.1 决定

`bundles/` 下建立三个子目录, 与 `bundles/base.yaml` 平级:
- `bundles/primitive/<name>.yaml` — Layer 1 原语图 (运行时原语, LCA 框架维护)
- `bundles/concept/<name>.yaml` — Layer 2 概念图 (领域概念, LCA 库维护)
- `bundles/business/<name>.yaml` — Layer 3 业务图 (业务编排, profile 维护)

每张图的 `id` 必须匹配:
- 原语图: `primitive.<domain>.<verb>` (e.g. `primitive.llm.call`)
- 概念图: `concept.<domain>.<verb>` (e.g. `concept.template.select`)
- 业务图: `business.<domain>.<noun>` (e.g. `business.reasoning.turn`)

`./scripts/lca-ops audit-bundle-node-naming` 新增 (本 PR 加), 校验三层前缀闭集 + 节点命名闭集 (`tool.*` / `prompt.*` / ...) + 禁词 (`process` / `handle` / `manage` / ...)。

### 3.2 原语图清单 (Layer 1)

| 图 id | 节点数 | 职责 |
|---|---|---|
| `primitive.llm.call` | 1 (`llm.invoke`) | 调一次 LLM + ModelVisible ContextVar + spine EP |
| `primitive.capability.fork` | 3 (`capability.bindings.read` / `capability.fork.dispatch` / `capability.forked.materialize`) | 任意 boot-time capability → per-run 实例 |
| `primitive.spine.emit` | 2 (`spine.event.compose` / `spine.event.dispatch`) | typed fact → spine EP |
| `primitive.typed.transform` | 1 (`dto.map.apply`) | 纯 typed DTO 映射 (无 I/O) |

**复用价值**:
- `primitive.llm.call` 被 `business.reasoning.turn` (调一次) + `concept.reflection.critique` (调一次) 复用 — 当前两处复制 LLM 边界逻辑
- `primitive.capability.fork` 被 `concept.tool.fork` + `concept.memory.snapshot` (新) 复用 — 当前两处反射 `fork_for_run`

### 3.3 概念图清单 (Layer 2)

| 图 id | 节点数 | 职责 | 消费的业务图 |
|---|---|---|---|
| `concept.tool.fork` | 3 (`tool.bindings.snapshot` / `tool.fork.dispatch` / `tool.shapes.normalize`) | ToolsService → ForkedTools | `business.reasoning.turn` |
| `concept.role.snapshot` | 2 (`role.profile.normalize` / `role.awareness.compose`) | RoleProfile + team_awareness → RoleSnapshot | `business.reasoning.turn` |
| `concept.context.compose` | 2 (`context.lines.collect` / `context.skills.merge`) | ContextManifest + task + skills → ReasonerContext | `business.reasoning.turn` |
| `concept.template.select` | 3 (`template.candidate.enumerate` / `template.candidate.score` / `template.candidate.pick`) | state + ReasonerContext → TemplateSelection | `business.reasoning.turn` |
| `concept.prompt.render` | 3 (`prompt.sections.assemble` / `prompt.sections.fill` / `prompt.trace.compile`) | ReasonerContext + TemplateSelection + RoleSnapshot → ReasonerTurnRender | `business.reasoning.turn` |
| `concept.decision.classify` | 3 (`decision.parse.tool_calls` / `decision.parse.intent` / `decision.compose.action`) | LLMResponse + ReasonerContext → Decision | `business.reasoning.turn` |
| `concept.decision.enforce` | 2 (`gate.chain.run` / `gate.chain.reject`) | candidate Decision + gate chain → enforced Decision | `business.reasoning.turn` |
| `concept.decision.shortcut_try` | 1 (`shortcut.try`) | state → Decision \| None | `business.reasoning.shortcut` |
| `concept.reflection.critique` | 2 (`reflect.observation.build` / `reflect.critique.run`) | EffectReceipt → Reflection | `business.reflection.turn` |
| `concept.memory.write` | 2 (`memory.admit.policy` / `memory.write.dispatch`) | Reflection → MemoryReceipt | `business.memory.turn` |
| `concept.stop.should_check` | 2 (`stop.should.decide` / `stop.focus.converge`) | state + governance → StopPayload | `business.stop.turn` |

**关键**:
- 节点 id 第一层动作域必须落在闭集 (§0.4 N9)
- 节点数 ≤ 4, 不允许单节点超过 6 节点的图 (违反 G1)
- 每张概念图有 `inputs:` / `outputs:` 显式声明 port + typed DTO

### 3.4 业务图清单 (Layer 3)

| 图 id | 节点数 | 职责 |
|---|---|---|
| `business.perceive.turn` | 4 (`perceive.input.collect` / `perceive.sensor.run` / `perceive.observation.fold` / `perceive.manifest.compose`) | run_input + memory → ContextManifest |
| `business.reasoning.turn` | 8 (`reason.prepare.tools` / `reason.prepare.role` / `reason.prepare.context` / `reason.prepare.template` / `reason.render.prompt` / `reason.llm.call` / `reason.classify.response` / `reason.gate.enforce`) | 8 个概念/原语图引用 → Decision |
| `business.reasoning.shortcut` | 1 (`shortcut.try`) | 概念图引用 → Decision (无 LLM) |
| `business.action.turn` | 3 (`act.action.resolve` / `act.capability.grant` / `act.effect.execute`) | Decision → EffectReceipt |
| `business.reflection.turn` | 1 (`reflect.critique.run`) | EffectReceipt → Reflection |
| `business.memory.turn` | 1 (`memory.write.dispatch`) | Reflection → MemoryReceipt |
| `business.stop.turn` | 1 (`stop.should.decide`) | state + governance → StopPayload |
| `business.run.phase` | 7 (`perceive.turn` / `reason.turn` / `act.turn` / `reflect.turn` / `remember.turn` / `stop.decide` / `loop.back`) | 6 phase + 1 loop back 边, 一次完整 run |

**关键**:
- 业务图节点 = `ref: <graph_id>` 引用, 不写实现
- `business.run.phase` 是顶层 phase 图, `interpreter` 只跑这一张图, 完全不知道 `think` / `act` 字面 (强化 ADR-0219 N1)
- profile 换业务 = 换 `business.run.phase` 引用的子图, 不动 `business.run.phase` 拓扑

### 3.5 delete-when

`bundles/think.yaml` / `bundles/think_reason.yaml` / `bundles/perceive.yaml` (旧) / `bundles/declarative-phase-graph.yaml` 删除时间点: P10 全部 PR 合并后, 同一 PR 内删 (`AGENTS.md` §4 COMPAT 原则)。无 delete-when 兼容分支 = 红灯。

---

## 4. 11 个 boundary typed DTO

### 4.1 决定

`lca/contracts/models/cognition/boundary.py` 新建, 集中定义所有跨图 boundary DTO:

```python
# lca/contracts/models/cognition/boundary.py (NEW)
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.delegation.delegation import TeamAwareness
from lca.contracts.models.cognition.skill import ActivatedSkill
from lca.contracts.models.cognition.template import TemplateSelection
from lca.contracts.models.cognition.reasoner_turn import (
    ReasonerContext, ReasonerTurnRender,
)
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.protocols import Tool


class BindingsView(BaseModel):
    """per-run bindings 视图, 由 RuntimePlane 在每 turn 暴露.

    替代 AgentState._xxx_ref 系列私有属性; ToolsService.fork_for_run 接
    BindingsView typed, 不接 Any / 不反射 state 私有属性.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    file_store: FileStore | None = None
    sandbox: Sandbox | None = None
    skill_store: SkillStore | None = None
    machine_resolver: MachineResolver | None = None
    search: SearchService | None = None
    bindings: Bindings | None = None


class ForkedTools(BaseModel):
    """per-run tool 列表, 替代反射 dict.

    binding_keys 显式记录绑了哪些 per-run ref; 下游消费者静态知道绑了什么.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: tuple[Tool, ...]
    binding_keys: frozenset[str]


class RoleSnapshot(BaseModel):
    """RoleProfile + team_awareness 冻结."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: RoleProfile
    team_awareness: TeamAwareness | None


class ReasonerBundle(BaseModel):
    """prep.graph → think.graph 的 typed bridge.

    4 个字段一次性携带 think 完整输入, 不允许 think 节点自己再反射拼装.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    tools: ForkedTools
    role: RoleSnapshot
    context: ReasonerContext
    template: TemplateSelection


# Decision / EffectReceipt / Reflection / MemoryReceipt / StopPayload
# 已存在于 contracts/models/{action,effect,reflection,memory,stop}/,
# 但需要审计是否满足 frozen + extra=forbid; 不满足的同 PR 修复.
```

### 4.2 boundary DTO 清单

| Boundary | 现有位置 | 本 ADR 调整 |
|---|---|---|
| `BindingsView` | (新) | 新建 |
| `ForkedTools` | (新) | 新建 |
| `RoleSnapshot` | (新) | 新建 |
| `ReasonerContext` | `cognition/reasoner_turn.py` | 审计 + 补 `frozen=True` + `extra="forbid"` |
| `TemplateSelection` | `cognition/prompt_assembly.py` | 审计 + 补 `frozen=True` + `extra="forbid"` |
| `ReasonerTurnRender` | `cognition/reasoner_turn.py` | 审计 + 补 `frozen=True` + `extra="forbid"` |
| `Decision` | `action/decision.py` | 审计 + 补 `frozen=True` + `extra="forbid"` |
| `EffectReceipt` | `effect/receipt.py` | 审计 + 补 `frozen=True` + `extra="forbid"` |
| `Reflection` | `reflection/model.py` | 审计 + 补 `frozen=True` + `extra="forbid"` |
| `MemoryReceipt` | `memory/receipt.py` | 审计 + 补 `frozen=True` + `extra="forbid"` |
| `StopPayload` | `stop/payload.py` | 审计 + 补 `frozen=True` + `extra="forbid"` |

**11 个 boundary DTO** (含 `BindingsView`)。

### 4.3 boundary 命名规范

| 命名要求 | 例 |
|---|---|
| 业务名, 不是 DTO 类型名 | `BindingsView` 不是 `RuntimeBindingsDTO` |
| 名字说 "是什么", 不说 "怎么做" | `ForkedTools` 不是 `ToolsForkedFromService` |
| 不带 phase / phase-region 前缀 | `Decision` 不是 `ThinkOutputDecision` |

### 4.4 delete-when

`BindingsView` 替代 `AgentState._xxx_ref`: P7 同 PR 删除。`ForkedTools` 替代 `_resolve_tools` 反射: P5 同 PR 删除。

---

## 5. `business.reasoning.turn` 业务图

### 5.1 决定

`bundles/business/reasoning_turn.yaml` 是核心业务图, 组合 8 个概念/原语图:

```yaml
# bundles/business/reasoning_turn.yaml
id: business.reasoning.turn
region: business
purpose: 一个 turn 的认知流 — 准备 4 DTO → 渲染 → 调 LLM → 分类 → gate

inputs:
  - port: bindings        # port type: BindingsView
  - port: llm             # port type: LLMAdapter (capability ref)
  - port: tools           # port type: ToolsService (capability ref)
  - port: role            # port type: RoleProfile (capability ref)
  - port: selector        # port type: PromptTemplateSelector (capability ref)
  - port: state           # port type: AgentState

nodes:
  # prep 阶段 — 4 个 DTO 并行可 fan-out (实际 driver 调度顺序无要求)
  - id: reason.prepare.tools    # ref: concept.tool.fork
  - id: reason.prepare.role     # ref: concept.role.snapshot
  - id: reason.prepare.context  # ref: concept.context.compose
  - id: reason.prepare.template # ref: concept.template.select

  # render 阶段
  - id: reason.render.prompt    # ref: concept.prompt.render

  # LLM 阶段
  - id: reason.llm.call         # ref: primitive.llm.call

  # 收尾阶段
  - id: reason.classify.response # ref: concept.decision.classify
  - id: reason.gate.enforce      # ref: concept.decision.enforce

edges:
  - reason.prepare.tools    → reason.render.prompt
  - reason.prepare.role     → reason.render.prompt
  - reason.prepare.context  → reason.render.prompt
  - reason.prepare.context  → reason.prepare.template
  - reason.prepare.template → reason.render.prompt
  - reason.render.prompt    → reason.llm.call
  - reason.prepare.tools    → reason.llm.call
  - reason.llm.call         → reason.classify.response
  - reason.classify.response → reason.gate.enforce

outputs:
  - port: decision
    type: Decision
```

### 5.2 关键变化 vs 当前 `think.yaml`

- 节点数: 5 → 8 (prep 4 + render 1 + LLM 1 + classify 1 + gate 1)
- 每个节点是 `ref:` 引用, 不写实现
- 4 个 prep 节点 fan-out 可并行 (driver 实现负责, 不在本 ADR 范围)
- tools 同时流向 `reason.render.prompt` (供 prompt 渲染时知道 tools 数量) 和 `reason.llm.call` (供 LLM 调用)

### 5.3 与 `business.run.phase` 的关系

`business.run.phase` 的 `reason.turn` 节点 = `subgraph_ref:` 指向 `business.reasoning.turn`, 沿用 ADR-0218 的 v2 subgraph driver。

### 5.4 delete-when

`bundles/think.yaml` / `bundles/think_reason.yaml`: P8 同 PR 删除。

---

## 6. `PromptReasoner` 类减肥

### 6.1 决定

`lca/cognition/brain/reasoner/reasoner.py` 从 544 行缩到 ≤ 280 行, 类从 7 方法 + 5 私有成员缩到 **2 公开方法 + 4 boot-time singleton ref**:

```python
# lca/cognition/brain/reasoner/reasoner.py (AFTER)
class PromptReasoner:
    """think.reason.render 和 think.reason.complete 节点的 reasoner 实例.

    只负责两个职责: render prompt (走 PromptAssembler), call LLM.
    不选模板, 不 fork tools, 不冻结 role, 不拼 context — 这些都是
    concept.* 图节点的职责. boot-time 由 phase.think.reasoner.compose 提供.
    """
    def __init__(
        self,
        llm: LLMAdapter,
        role_profile: RoleProfile,
        *,
        assembler: PromptAssembler | None = None,
    ) -> None:
        self.llm = llm
        self.role_profile = role_profile
        self.assembler = assembler

    def render_turn(
        self,
        context: ReasonerContext,
        template: TemplateSelection,
        role: RoleSnapshot,
    ) -> ReasonerTurnRender:
        """概念图节点 reason.render.prompt 的实现."""
        ...

    async def complete_turn(
        self,
        render: ReasonerTurnRender,
        tools: ForkedTools,
        step: StepCursor,
    ) -> LLMResponse:
        """原语图节点 llm.invoke 的实现."""
        ...
```

### 6.2 删除清单 (同 PR)

- `_tools_service` 私有属性
- `_resolve_tools` 私有方法 (30 行反射)
- `_legacy_select_template` 私有方法
- `_legacy_variables` 私有方法
- `_legacy_templates` 私有 dict
- `available_skills` 公开属性
- `tools_desc` / `catalog` / `tools` 公开属性
- `_available_skills_count_hint` / `_template_section_names` / `_template_variant` 三个私有方法
- `_bind_reasoner_prompt` / `_reset_reasoner_prompt` / `_step_id_for_trace` 三个 ContextVar 私有方法 → `primitive.llm.call` 节点负责
- `register_template` / `build_turn_plan` / `generate_thoughts` 三个公开方法
- `_select_template` / `_render_prompt` 私有方法 → `concept.template.select` / `concept.prompt.render` 节点负责
- `_role_prompt_vars` 顶级 helper → 删除 (legacy 死代码, 走 `concept.prompt.render` 的 sections)

### 6.3 ModelVisible ContextVar 移交

`_bind_reasoner_prompt` / `_reset_reasoner_prompt` 移到 `primitive.llm.call` 节点, 由 `lca.primitives.llm.invoke` 实现。`step_id_for_trace` 同样移交。

### 6.4 delete-when

`cognition/brain/reasoner/reasoner.py` 全部上述删除: P9 同 PR。

---

## 7. `AgentState` 不持 ref

### 7.1 决定

`AgentState` 删除 5 个 `_xxx_ref` 私有属性:

```python
# lca/contracts/models/core/state/state.py (AFTER)
class AgentState(BaseModel):
    """业务状态 — 只携带业务数据, 不携带 capability ref."""
    # ... 保留业务字段 ...
    step: StepCursor
    task: str
    team_awareness: TeamAwareness | None
    activated_skills: tuple[ActivatedSkill, ...]
    decision: Decision | None
    # ... 其他业务字段 ...
    # 删除以下 5 个:
    # _file_store_ref: FileStore | None = None   ❌
    # _sandbox_ref: Sandbox | None = None          ❌
    # _skill_store_ref: SkillStore | None = None  ❌
    # _machine_resolver_ref: MachineResolver | None = None  ❌
    # _search_ref: SearchService | None = None    ❌
```

### 7.2 反射消费方删除

`reasoner.py:300-305` 的 `getattr(state, "_xxx_ref", None)` 6 行 → 删除。`ToolsService.fork_for_run(bindings_view)` 接 typed `BindingsView`, 不反射 state。

### 7.3 `BindingsView` 来源

`BindingsView` 由 `RuntimePlane.current_bindings()` 在每 turn 暴露, 由 `business.run.phase` 的 `bindings` port 注入到 `business.reasoning.turn`, 再由 `business.reasoning.turn` 注入到 `concept.tool.fork` 的 `bindings` input。

### 7.4 delete-when

5 个 `_xxx_ref` 属性 + `reasoner.py` 6 行反射消费: P7 同 PR。

---

## 8. `reasoner_provider.setup` 拆分

### 8.1 决定

`lca/plugins/think/reasoner_provider.py` (130 行) 拆为两个 plugin:

```python
# lca/plugins/think/reasoner/credentials.py (NEW, ~50 行)
@plugin(
    id="phase.think.reasoner.credentials",
    provides=("llm_adapter",),
    requires=(),
    layer="L1",
    kind=PluginKind.PROVIDER,
    ...
)
async def setup(ctx, config):
    api_key, base_url, model_from_env = llm_credentials()
    adapter = ProductionLLMResolver(...).resolve()
    ctx.provide("llm_adapter", adapter)


# lca/plugins/think/reasoner/compose.py (NEW, ~40 行)
@plugin(
    id="phase.think.reasoner.compose",
    provides=("reasoner",),
    requires=("llm_adapter", REASONER_ROLE_PROFILE.key, "tools"),
    layer="L1",
    kind=PluginKind.PROVIDER,
    ...
)
async def setup(ctx, config):
    llm = ctx.require("llm_adapter")
    role = ctx.require(REASONER_ROLE_PROFILE.key)
    tools = ctx.require("tools")  # 显式 require, 走 Cordis manifest 校验
    reasoner = PromptReasoner(llm=llm, role_profile=role, assembler=...)
    ctx.provide("reasoner", reasoner)
```

### 8.2 `bundles/base.yaml` 调整

```yaml
# bundles/base.yaml (AFTER)
entries:
  # 替换 - id: phase.think.reasoner
  # + id: phase.think.reasoner.credentials
  # + id: phase.think.reasoner.compose
```

### 8.3 delete-when

`lca/plugins/think/reasoner_provider.py`: P9 同 PR 删除。

---

## 9. 端到端验证

### 9.1 既有约束保持

- `./scripts/lca-ops runs create --user-text "ping" --wait --json` 跑通六语义 `perceive → think → act → reflect → remember → stop`
- `broken_hop=None`
- 不引入新的 capability 维度
- `PromptReasoner` 仍是唯一调 LLM 的 seam (走 `primitive.llm.call` 节点)

### 9.2 新增验证

- `tests/integration/think/test_business_reasoning_turn.py::test_e2e_with_prep_graph` — `business.reasoning.turn` 完整 e2e
- `tests/business/test_three_tier_graph_dispatch.py` — 三层图 dispatch 不交叉 (原语图不被业务图直接写, 概念图不被业务图写实现, 业务图只 `ref:`)
- `tests/contracts/test_boundary_dto_frozen.py` — 11 个 boundary DTO 全部 `frozen=True` + `extra="forbid"` 契约测试
- `tests/contracts/test_no_state_reflection.py` — `grep -rn "getattr(state, \"_" lca/ = 0`

---

## 10. 既有测试不退化

| 测试套 | 现状 | 本 ADR 后 |
|---|---|---|
| `tests/think/` | 21 个 | 全过, 不退化 |
| `tests/integration/think/` | 7 个 | 全过, 不退化 |
| `tests/harness/graph/execute/` | 18 个 | 全过, 不退化 |
| `tests/contracts/test_subgraph_reference_contract.py` | 5 个 | 全过, 不退化 |
| `tests/declarative/test_phase_graph.py` | 12 个 | 全过, 不退化 |
| **新增** | — | `tests/business/test_three_tier_graph_dispatch.py` (~8 个) |
| **新增** | — | `tests/contracts/test_boundary_dto_frozen.py` (~12 个) |
| **新增** | — | `tests/contracts/test_no_state_reflection.py` (~3 个) |
| **新增** | — | `tests/integration/think/test_business_reasoning_turn.py::test_e2e_with_prep_graph` (~4 个) |

**总测试数**: 现有 63 个不退化 + 新增 ~27 个 = ~90 个.

---

## 11. 实施分批 (P1—P10, 每批一个 PR)

| 批 | 内容 | diff | 风险 | 验证 |
|---|---|---|---|---|
| **P1** | 新建 `lca/contracts/models/cognition/boundary.py` + 11 个 boundary DTO (`BindingsView` / `ForkedTools` / `RoleSnapshot` / `ReasonerContext` / `TemplateSelection` / `ReasonerTurnRender` / `Decision` / `EffectReceipt` / `Reflection` / `MemoryReceipt` / `StopPayload`); 新增 `tests/contracts/test_boundary_dto_frozen.py` | +~300 | 低 | 新增契约测试 |
| **P2** | `bundles/primitive/` + `primitive.capability.fork` + `primitive.llm.call` 骨架 (impl 留 stub); `bundles/concept/` 目录 + `concept.tool.fork` 节点 (impl 走 `ToolsService.fork_for_run(BindingsView)` 新签名); 修改 `tools.py:73-89` `fork_for_run(bindings: BindingsView)` | +~450 / -~30 | 低 | `tests/primitive/test_capability_fork.py` |
| **P3** | `concept.role.snapshot` + `concept.context.compose` + `concept.template.select` 三张概念图 + `PromptTemplateSelector` provider | +~600 | 中 | `tests/concept/test_role_snapshot.py` + `test_context_compose.py` + `test_template_select.py` |
| **P4** | `concept.prompt.render` + `PromptReasoner.render_turn` 改签名 `(context, template, role) -> ReasonerTurnRender`; `_bind_reasoner_prompt` 移到 `primitive.llm.call` 节点 impl | +~400 / -~80 | 中 | `tests/concept/test_prompt_render.py` |
| **P5** | `business.reasoning.turn` + 8 个概念/原语图引用; 新建 `tests/integration/think/test_business_reasoning_turn.py`; 暂保留旧 `think.yaml` 不删 (compatibility 期内, profile 选 `business_run_v2` 走新路径) | +~300 | 中 | e2e |
| **P6** | `concept.decision.classify` + `concept.decision.enforce`; `think.classify` + `think.gate` 节点改 `ref:` 引用; `business.reasoning.shortcut` | +~500 | 中 | e2e |
| **P7** | `AgentState` 删除 5 个 `_xxx_ref`; `reasoner.py` 删除 `_resolve_tools` + 6 行 `getattr(state, ...)` 反射; `BindingsView` 由 `RuntimePlane.current_bindings()` 在每 turn 暴露; 新增 `tests/contracts/test_no_state_reflection.py` | +~150 / -~80 | 中 | `grep` 校验 + 全套回归 |
| **P8** | `business.perceive.turn` + `business.action.turn` + `business.reflection.turn` + `business.memory.turn` + `business.stop.turn` + `business.run.phase` (顶层 phase 图, 替换 `bundles/declarative-phase-graph.yaml` 的 `phase.topology.standard`); interpreter 升级跑 `business.run.phase` 单图 | +~700 / -~300 | 中 | 全套 e2e |
| **P9** | `PromptReasoner` 类减肥到 2 方法 + 4 boot singleton; `lca/plugins/think/reasoner_provider.py` 拆为 `credentials.py` + `compose.py`; `bundles/base.yaml` 替换 plugin id; 删除 `_legacy_*` / `_resolve_tools` / `_tools_service` 全部; `_strip_think_reason_complete` (plan_lift.py:95-115) 删除 (Default reasoner 现在能正确实现 `complete_turn` 因为 tools 走 boundary) | -~250 / +~150 | 高 | 全套 e2e + 既有 `tests/think/` 21 个不退化 |
| **P10** | 收尾: `cognitive_emit.run_reasoner_generate_thoughts_with_spine_facts` (cognitive_emit.py:380-432) duck-type 路径删除, 改走 `business.run.phase` 显式调度; `bundles/think.yaml` / `bundles/think_reason.yaml` / `bundles/declarative-phase-graph.yaml` 三个旧 bundle 删; `audit-bundle-node-naming` 脚本加进 `lca-ops` | -~250 / +~80 | 高(收尾) | 全套回归 + 既有 40 脚本门禁 |

**预计 10 PR**, 每个 PR 一张图 / 一个 boundary DTO / 一个收口动作, 每个 PR diff ≤ 600 行, 每个 PR 必带 verify command + 回归测试。

### 11.1 PR 之间的依赖

```
P1 (boundary DTO)
 │
 ├─► P2 (primitive.capability.fork + concept.tool.fork)
 │     │
 │     └─► P3 (concept.role.snapshot + concept.context.compose + concept.template.select)
 │           │
 │           └─► P4 (concept.prompt.render + PromptReasoner.render_turn 改签名)
 │                 │
 │                 └─► P5 (business.reasoning.turn)
 │                       │
 │                       └─► P6 (concept.decision.classify + concept.decision.enforce)
 │                             │
 │                             └─► P8 (其他业务图 + business.run.phase)
 │                                   │
 │                                   └─► P9 (PromptReasoner 减肥 + reasoner_provider 拆分)
 │                                         │
 │                                         └─► P10 (收尾删旧 bundle)
P7 (AgentState 删 ref) ─► P9 ─► P10
```

**关键依赖**: P7 不依赖 P2—P6, 可与 P2—P6 并行; P9 必须在 P5 + P6 + P7 之后; P10 必须在 P9 之后。

---

## 12. 与既有 ADR 的关系

| ADR | 本 ADR 与其的关系 |
|---|---|
| ADR-0217 Bundle Graph Schema v2 | ✅ 直接承接 — 用同样的 yaml schema 写更多图 |
| ADR-0218 Bundle Graph v2 Subgraph Driver | ✅ 直接承接 — `subgraph_ref:` 用于 `business.run.phase` 的 phase 节点嵌入子图 |
| ADR-0219 phase-graph unification | ✅ 强化 — interpreter 升级跑 `business.run.phase` 单图, 彻底不知道 `think` / `act` 字面 (强化 ADR-0219 N1); `RestrictedPhaseContext` 的 `Mapping[SemanticPhase, PhaseResult]` 改为 `Mapping[PhaseBoundaryName, BoundaryDTO]` (强化 ADR-0219 N3) |
| ADR-0035 Solo/Member/Lead Reasoner | ✅ 不破 — Profile 选择层, 不动图结构 |
| ADR-0075 默认 6 phase | ✅ 不破 — 6 phase 仍 6 phase, phase 现在是 "业务图" 而非 "plugin" |
| ADR-0074 Control plane | ✅ 不破 — control plugins 仍存在, 挂在图节点的 control slot |
| ADR-0156 eliminate projection leakage | ✅ 强化 — boundary DTO 是 typed projection, 不泄漏到 state |
| ADR-0186/0191/0192 Fact Gateway | ✅ 不破 — boundary DTO 跨图, 不跨事实; 事实仍走 FactGateway 单轨 |

---

## 13. 风险与拒绝项

### 13.1 风险

| 风险 | 缓解 |
|---|---|
| `PromptReasoner` 缩到 2 方法破坏既有测试 (21 个 think 测试) | P9 同 PR 改测试 + 增加 boundary test; 跑 `./scripts/lca-ops notes-check` 校验不留 compat shim |
| `business.run.phase` 替换 `phase.topology.standard` 破坏既有 profile | P8 同 PR 改 `bundles/declarative-phase-graph.yaml` 改为 `business_run_v2`; 老 profile 走 compat 期临时保留, P10 删 |
| `ToolsService.fork_for_run(bindings: BindingsView)` 新签名破坏既有 `ToolFactory.bind(run: Any)` 实现 | P2 同 PR 改所有 `ToolFactory.bind` 实现接 `BindingsView`; 列 audit 清单 (lca/plugins/tools/*) |
| `AgentState` 删 5 个 `_xxx_ref` 破坏既有反射读 | P7 同 PR grep 全代码库找到所有反射读, 全部改为走 `BindingsView` |
| 图层 schema 增加 `PluginKind` 一等公民可能影响 `audit-plugin-shape` | P10 同 PR 改 `scripts/lca-ops` 加 `audit-bundle-node-naming` 子命令 |

### 13.2 拒绝项

| 提案 | 为什么拒 |
|---|---|
| 把 `PromptReasoner` 拆成 3 个 plugin (`build_turn_plan_provider` / `render_turn_provider` / `complete_turn_provider`) | 三个方法共享 `assembler` / `role_profile`, 各自 plugin 会重复持有 seam; 一个类持 4 个 boot singleton ref 是合理的, 拆成 3 plugin = seam 反而裂开 |
| 把 `prep` 做成 think 子图的前置节点 (而不是独立图) | 隐式把 "准备" 塞进 think, 违反 G1 一张图 = 一个职责, perceive → think 之间没有显式 boundary |
| 只删 `_resolve_tools` 但保留 `_legacy_*` fallback | 违反 C6 最小化, fallback 是 dead path, 删除才彻底 |
| 保留 `state._xxx_ref` 但让 `PromptReasoner` 不反射读 | 违反 boundary discipline, state 仍是隐式 seam 容器, 下次还会有人反射读别的 ref |
| 把 `ForkedTools.items` 写成 `list[Tool]` 而不是 `tuple[Tool, ...]` | tuple 是 frozen + hashable, 与 `extra="forbid"` 一致; list 可变, 与 frozen 矛盾 |
| 把 `business.run.phase` 的 phase 节点写成 `sub_spec_ref:` 而不是 `subgraph_ref:` | ADR-0218 已经合并, subgraph_ref 是 v2 标准, sub_spec_ref 是 v1 兼容路径 |

### 13.3 Open questions (评审时讨论)

1. `concept.role.snapshot` 是否需要分 `role.profile.normalize` 和 `role.awareness.compose` 两个节点, 还是合并成一个 `role.snapshot.compose`? 当前建议拆分 (G1 职责单一)
2. `business.reasoning.turn` 的 prep 4 节点 fan-out 是否需要 driver 显式支持并行调度? 当前 driver 是顺序, fan-out 由 YAML 拓扑表达; 并行是 driver 优化, 不是本 ADR 范围
3. `primitive.llm.call` 是否需要支持 stream 输出? 当前 LLMResponse 是最终响应, stream 由 transport 层负责; 本 ADR 不破既有
4. 11 个 boundary DTO 是否拆到独立文件 (`boundary_bindings.py` / `boundary_thinking.py` / ...) 还是集中一个 `boundary.py`? 当前建议集中, 但 DTO 多 (>20) 后拆

---

## 14. Acceptance criteria 之外的验证

除 §闸门 1-9 外, 以下 grep 校验必须在每个 PR 末尾跑过且 = 0:

```bash
# N7 三层图 schema
find bundles -maxdepth 1 -name "*.yaml" | grep -v "^bundles/base.yaml$" | grep -v "^bundles/\(primitive\|concept\|business\)/"  # = 0

# N8 boundary typed DTO frozen
grep -rn "dict\[str, Any\]" lca/contracts/models/cognition/boundary.py  # = 0
grep -n "frozen=False\|extra=\"ignore\"" lca/contracts/models/cognition/boundary.py  # = 0

# N9 节点命名闭集
grep -rn "id: [a-z_]*\.process\b\|id: [a-z_]*\.handle\b\|id: [a-z_]*\.manage\b\|id: do_" bundles/primitive bundles/concept bundles/business  # = 0

# N10 PromptReasoner 类减肥
grep -n "def " lca/cognition/brain/reasoner/reasoner.py  # = 4
wc -l lca/cognition/brain/reasoner/reasoner.py  # ≤ 280

# 反射归零
grep -rn 'getattr(state, "_' lca/  # = 0

# 偷 inject 归零
grep -rn "runtime().inject(" lca/plugins/  # = 0

# legacy dead path 归零
grep -rn "self\._legacy_\(select_template\|variables\|templates\)" lca/  # = 0

# spine reflector legacy 归零
grep -rn "spine_reflector_" lca/  # = 0 (ADR-0194 P5 已落地, 本 ADR 强化)

# artifact 字符串 key 归零
grep -rn 'artifacts\["think"\]\|artifacts\.get("think")' lca/ plugins/  # = 0 (ADR-0219 §10 已要求)
```

---

## 15. 一句话总结

把 LCA 图家族从 "代码分组" 重构成 "概念群": **三层图 + 11 个 boundary typed DTO + PromptReasoner 减肥到 2 方法 + AgentState 不持 ref + reasoner_provider 拆分**。读 `bundles/business/reasoning_turn.yaml` 就理解一次认知 turn。10 个 PR, 每个 ≤ 600 行, 每个带 e2e + 回归。

---

**附录 A — 三层图拓扑速查**

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: business.*           (profile 维护, 业务编排)        │
│   business.run.phase          (顶层, interpreter 跑这张)     │
│     ├─ business.perceive.turn                                 │
│     ├─ business.reasoning.turn ─┐                             │
│     │   ├─ reason.prepare.tools ─┤                             │
│     │   │  └─► concept.tool.fork                               │
│     │   │       └─► primitive.capability.fork                  │
│     │   ├─ reason.prepare.role   ─► concept.role.snapshot      │
│     │   ├─ reason.prepare.context► concept.context.compose     │
│     │   ├─ reason.prepare.template► concept.template.select   │
│     │   ├─ reason.render.prompt  ─► concept.prompt.render      │
│     │   ├─ reason.llm.call       ─► primitive.llm.call         │
│     │   ├─ reason.classify.response► concept.decision.classify │
│     │   └─ reason.gate.enforce   ─► concept.decision.enforce   │
│     ├─ business.action.turn                                     │
│     ├─ business.reflection.turn ─► concept.reflection.critique │
│     ├─ business.memory.turn     ─► concept.memory.write        │
│     └─ business.stop.turn       ─► concept.stop.should_check   │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: concept.*            (LCA 库维护, 领域概念复用)       │
│   11 张概念图, 见 §3.3                                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: primitive.*          (框架维护, 原子原语)            │
│   primitive.llm.call                                         │
│   primitive.capability.fork                                  │
│   primitive.spine.emit                                       │
│   primitive.typed.transform                                  │
├─────────────────────────────────────────────────────────────┤
│ Capability seams (boot-time, 不是图, 是 RuntimePlane 注册)     │
│   LLMAdapter / ToolsService / RoleProfile /                  │
│   PromptTemplateSelector / MemorySystem / PerceiveHub /      │
│   Critic / DecisionGate / SkillRouter                        │
└─────────────────────────────────────────────────────────────┘
```

---

**附录 B — 11 个 boundary DTO 速查**

| Boundary | 类型 | 生产者图 | 消费者图 |
|---|---|---|---|
| `BindingsView` | per-run bindings | `RuntimePlane.current_bindings()` | `business.reasoning.turn` / `concept.tool.fork` |
| `ForkedTools` | per-run tool 列表 | `concept.tool.fork` | `business.reasoning.turn` → `primitive.llm.call` |
| `RoleSnapshot` | role 冻结 | `concept.role.snapshot` | `business.reasoning.turn` → `concept.prompt.render` |
| `ReasonerContext` | context 组合 | `concept.context.compose` | `business.reasoning.turn` → `concept.prompt.render` / `concept.template.select` |
| `TemplateSelection` | 模板选择 | `concept.template.select` | `business.reasoning.turn` → `concept.prompt.render` |
| `ReasonerBundle` | 4 DTO bundle | `business.reasoning.turn` prep 阶段 | `business.reasoning.turn` render 阶段 |
| `ReasonerTurnRender` | 渲染结果 | `concept.prompt.render` | `business.reasoning.turn` → `primitive.llm.call` |
| `Decision` | 决策 | `concept.decision.classify` / `concept.decision.shortcut_try` / `concept.decision.enforce` | `business.reasoning.turn` → `business.action.turn` |
| `EffectReceipt` | 执行回执 | `concept.effect.execute` | `business.reflection.turn` |
| `Reflection` | 反思 | `concept.reflection.critique` | `business.memory.turn` |
| `MemoryReceipt` | 记忆回执 | `concept.memory.write` | `business.stop.turn` |
| `StopPayload` | 终止载荷 | `concept.stop.should_check` | `business.run.phase` loop back 边 |