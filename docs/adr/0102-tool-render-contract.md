# ADR-0102: Tool Render Contract —— 六层隐式契约坍缩成一个 typed contract

## 状态

**Accepted — 2026-08-29。** 实现见 commits `e4026c8a`..`266babe5`（8 commits，main 分支）。

承接 ADR-0101（tool 事件回归事实账本）。本 ADR 解决 ADR-0101 留下的最后一个未解问题：**renderer 与 backend Tool 之间的字段命名契约散落在 6 层隐式逻辑里**。

> **核心决策：每个 LCA Tool 显式声明一个 `RenderContract`（Python dataclass）——args 形状、state 形状、字段重命名、wire_key。后端 codegen 生成 TS 契约表，前端 `projectToolCall()` 是唯一一处把 ToolInvoked 投影成 LobeHub pluginState 的逻辑。**`argv-style 7 键白名单`、`__state_ref__` 占位、`buildToolState` 提拉、`translateSessionFrame` 7 类翻、双 wire path 全部退役。

---

## 0. 阅读顺序

1. §1 现象 —— 7 个具体故障点
2. §2 第一性原理 —— 为什么 6 层默契必然崩
3. §3 一次性方案 —— typed contract
4. §4 contract schema
5. §5 实施落点
6. §6 增量风险 vs 全量重写
7. §7 与既有 ADR 的关系
8. §8 验收规约

---

## 1. 现象（7 个具体故障点）

实测 8.21 LobeHub 渲染层与 LCA 后端 Tool 层的字段错位（部分出现在 `deploy/lobehub/CUSTOMIZATIONS.md` 已知问题里）：

| # | Tool | 现象 | 根因 |
|---|---|---|---|
| 1 | `activate_skill` | args 折叠卡显示空白，但 content 渲染正确 | `skill_id` 写的是 `name`，前端 `pickArgs` 找不到 |
| 2 | `read_skill_reference` | 整卡 return null 不显示 | `if (!path || !content) return null`；state 没回填 `path` |
| 3 | `run_skill_script` | execScript 渲染但 command 取自 `args.script` 而 LCA 给的是 `args.command` | 字段名错位 |
| 4 | `executeCode` / `runCommand` | 流式 stdout 在 ToolInvoked 落地后被覆盖 | `optimisticUpdatePluginState(state)` 全量替换，`state={}` 把累积擦掉 |
| 5 | `import_skill` | render 后端写 `importSkill`，但前端条件分支硬编码 `importFromMarket` | WIRE 表外的特例 |
| 6 | 全部 Tool | argv-style 仅 lift 7 键（`code/command/language/skill_id/description/execution_env/output_text`） | `journal_lifting.py` 硬编码白名单 |
| 7 | 新 Tool 上线 | 改 5+ 文件：tool 实现、wire 表、journal_lifting、buildToolState、translateSessionFrame、Renderer | 6 处默契对齐 |

每条都是"默契补丁"——一个错位就要在 6 处里翻。累计 7+ 文件 + 3+ 测试 fixture 跟着走。

---

## 2. 第一性原理

LCA 与 LobeHub 是两个独立系统，跨边界传递事实时，**字段命名 + 字段形状 + 字段来源**三件事必须有一边显式声明。LCA 当前选择的是"LobeHub 端靠默契读"——这种选择在边界增长时一定崩，因为：

1. **契约不能从代码推断**：LCA Tool 的 Observation.payload 是 `dict[str, Any]`，可以放任何字段。"前端 renderer 读什么"是个**跨系统问题**，单看任一侧都看不出来。
2. **白名单是 ad-hoc 协议**：`journal_lifting.py` 的 7 键白名单是 8.21 LobeHub 当时的渲染需求快照，扩展工具时必然漏。
3. **三层重复同一份信息**：Python Tool 知道 args/state、wire 表知道 identifier/apiName、Renderer 知道 args.X 怎么读。三个 SSOT 一改就要三改。
4. **双 wire path 是历史包袱**：legacy Journal path（args inline）和 Session Spine path（args 仅 ref），前端要分两条路径翻译。

第一性结论：**boundary 必须是 typed contract，contract 必须在发出侧（Python）声明，接收侧（TS）codegen**。

---

## 3. 一次性方案

### 3.1 Tool 侧声明 contract

每个 Tool 类加一个 `render = RenderContract(...)` 类属性：

```python
@contract(
    RenderContract(
        tool_name="activate_skill",
        identifier="lobe-skills",
        api_name="activateSkill",
        args=(COMMON["skill_id"].rename("name"),),  # LCA python_key → LobeHub wire_key
        state=(
            COMMON["name"],
            COMMON["title"],
            COMMON["description"],
            COMMON["has_resources"],
        ),
        content_field="content",  # SKILL.md 正文走顶层 content
    )
)
class SkillActivateTool(Tool):
    name = "activate_skill"
    ...
```

contract 一次写好，**LCA 后端 / codegen TS / frontend projection / LobeHub renderer** 四个消费者都从同一份表读。

### 3.2 Backend 投影

`emit_tool_invoked()` 在事件 emit 前调 `project_tool_state(tool_name, args, observation)`，把结果挂到 `ToolInvoked.projected_state`（SSE-only 字段）。`JsonlJournalProjector._write()` 落盘前 `_strip_sse_only_fields()` 剥离，jsonl 仍是事实账本。

### 3.3 Frontend 单一投影

`lcaToolRender/projection.ts:projectToolCall(toolName, startedData, invokedData)` —— ONE function，根据 contract 走两条路：

1. **优先**：读 `invokedData.projected_state`（backend 已经按 contract 渲染好，wire_key 直接是 LobeHub 期望的）
2. **回退**：从 `invokedData` 顶层按 contract.state 的 `python_key` 读，套上 wire_key 重命名

Renderer 组件不再需要关心 contract —— 只读 `args.X` 和 `pluginState.X`，命名由 contract 锁定。

### 3.4 Codegen

`lca/infrastructure/tools/contract/codegen_ts.py:render_registry_to_ts()` 输出 `deploy/lobehub/patches/runtime/lcaToolRender/contracts.generated.ts`。**Python REGISTRY 是 SSOT，TS 表每次改 Python 都重新生成**。

---

## 4. Contract schema

```python
@dataclass(frozen=True, slots=True)
class FieldSpec:
    python_key: str  # Tool Observation.payload / args 里的键
    wire_key: str  # SSE / Renderer 看到的键（已 camelCase）
    kind: Literal["string", "int", "bool", "json", "file_ref", "content_ref"]
    source: Literal["argument", "observation", "evidence_ref", "constant"]
    required: bool = True
    description: str = ""
    # helpers:
    #   .rename(new_wire_key) — 一行改名
    #   .optional()           — required=False


@dataclass(frozen=True, slots=True)
class RenderContract:
    tool_name: str  # LCA 工具名（Python Convention）
    identifier: str  # LobeHub builtin identifier (e.g. "lobe-skills")
    api_name: str  # LobeHub apiName (e.g. "activateSkill")
    args: tuple[FieldSpec, ...]  # 调用参数
    state: tuple[FieldSpec, ...]  # 终态 pluginState
    streaming: tuple[FieldSpec, ...] = ()  # SandboxOutputDelta 等流式字段
    content_field: str | None = None  # Observation.payload 里 message content 的 key
    wait_for: tuple[str, ...] = ()  # 需要等到哪些 ref 落地


REGISTRY: dict[str, RenderContract] = {}  # tool_name → contract
```

### 4.1 不变量

| # | 规则 |
|---|---|
| 1 | 任何 Tool 必须 `render = RenderContract(...)`，否则 `record()` 抛 `KeyError`（registry 时 fail-fast） |
| 2 | wire_key 必须是 camelCase（`^[a-z][a-zA-Z0-9]*$`），LobeHub pluginState 访问语义要求 |
| 3 | required + missing → 不发射键；optional + missing → 发射 `null`（让 frontend 知道 slot 存在） |
| 4 | `evidence_ref` source 在 backend 不参与投影，前端如需 fetch 走 `EvidenceRunner` |
| 5 | jsonl 永远不带 `projected_state`（`_SSE_ONLY_FIELDS = {"projected_state"}` 集中维护） |
| 6 | codegen 输出确定性：相同 REGISTRY 两次调用 byte-for-byte 相同 |

---

## 5. 实施落点

### 5.1 新增模块

```
lca/infrastructure/tools/contract/
├── __init__.py            # 重新导出
├── render.py              # FieldSpec, RenderContract, REGISTRY, @contract, get_contract
├── schema.py              # COMMON 字段表（≥35 个 LCA 已知字段）
├── builtin.py             # sandbox_state(), skill_args(), skill_state() 工厂
├── codegen_ts.py          # render_registry_to_ts() → 稳定 TS literal
├── project.py             # project_args/state/content/full(args, observation)
└── sandbox_contracts.py   # 13 cloud-sandbox + 12 local-system 工具动态注册
```

### 5.2 改动文件

| 文件 | 改动 |
|---|---|
| `lca/cognition/body/tool_journal_emit.py` | `emit_tool_invoked` 调 `project_tool_state()` 并挂 `projected_state` |
| `lca/contracts/models/observability/journal.py` | `ToolInvoked` 加 `projected_state: Mapping[str, object] = {}` |
| `lca/infrastructure/observability/journal/jsonl_projector.py` | `_write` 调用 `_strip_sse_only_fields()` 落盘前剥离 |
| `gateway/runs/query_endpoints.py` | `stream_run_live` 不再 wrap `iter_lifted_journal_sse` |
| `deploy/lobehub/patches/runtime/LcaRunDriver.ts` | ToolInvoked 分支优先读 `projected_state`，回退到老路径 |
| `deploy/lobehub/patches/runtime/lca_tool_render.py` | 新 patch metadata 文件 |

### 5.3 新增前端模块

```
deploy/lobehub/patches/runtime/lcaToolRender/
├── contracts.generated.ts          # 自动生成（codegen）
├── projection.ts                   # ONE projectToolCall() 函数
├── projection.test.ts              # 16 vitest
├── evidence.ts                     # EvidenceRunner + parseEvidenceRef
├── index.ts                        # facade 导出
└── renderers/
    ├── index.ts                    # LCARenderers 注册表
    ├── _shell.tsx                  # 共享 UI shell
    ├── lobe-cloud-sandbox/         # 13 个 renderer（executeCode/runCommand/readFile/...）
    ├── lobe-local-system/          # 12 个 re-export
    ├── lobe-skills/                # 4 个（activateSkill/runSkill/execScript/readReference）
    ├── lobe-skill-store/           # 3 个（importSkill/importFromMarket/searchSkill）
    ├── lobe-web-browsing/search.tsx
    └── lobe-user-interaction/askUserQuestion.tsx
```

### 5.4 删除文件

- `gateway/runs/journal_lifting.py` —— argv-style lift 不再需要
- `deploy/lobehub/patches/runtime/lcaJournal.ts` —— legacy Journal 投影（保留作 fallback 路径调用方，但本身不再有 SSOT）
- `deploy/lobehub/patches/runtime/lcaWire.ts` —— WIRE 表由 contract 取代
- `deploy/lobehub/patches/runtime/.generated/lcaJournal.generated.ts` —— codegen 替代
- `deploy/lobehub/patches/ui/RunCommandRender.tsx` / `ExecuteCodeRender.tsx` —— 迁到 `lcaToolRender/renderers/lobe-cloud-sandbox/`

### 5.5 测试

- `tests/tools/test_render_contract.py` — 11 测试：registry/codegen/FieldSpec helpers
- `tests/tools/test_tool_contracts_registered.py` — 13 测试：32 个 Tool 都在 REGISTRY、字段命名、identifier 正确
- `tests/tools/test_project_tool_state.py` — 19 测试：projection 各种 source、missing handling、content field
- `tests/tools/test_render_contract_reconciliation.py` — 68 参数化测试：每个 contract 都有 renderer、wire_key 都是 camelCase、特定 rename 命中
- `deploy/lobehub/patches/runtime/lcaToolRender/projection.test.ts` — 16 vitest

---

## 6. 增量风险 vs 全量重写

| 选项 | 风险 | 代价 |
|---|---|---|
| **全量重写 lcaJournal.ts** | LobeHub AgentRuntime 假设破坏、e2e 流程回归 | 高，需要 e2e 测试覆盖 |
| **增量保留老路径作为 fallback** ✓ | 老路径继续存在 ~1 个版本周期 | 低（已采用） |

**采用增量**：LcaRunDriver 的 ToolInvoked 分支先看 `projected_state`，有就消费，没有就回退 `projected.state`（老 buildToolState）。所有 Tool 都注册 contract 后，老路径无消费者，自然废退。下一步 Task 8 可删 `lcaJournal.ts`。

---

## 7. 与既有 ADR 的关系

| ADR | 关系 |
|---|---|
| ADR-0101 tool-facts-and-evidence-only | **直接承接**。本 ADR 解决 ADR-0101 留下"renderer 怎么知道读什么"的开放问题 |
| ADR-0100 chat-command-is-agent-run | 不变。命令面仍是 `POST /runs` |
| ADR-0099 runs-live-openai-stream | 不变。OpenAI 兼容管家面独立 |
| ADR-0098 session-spine-deltas | 不变。Session Spine 仍然发 `event: deltas` 通道；本 ADR 解决的是 legacy Journal 路径的字段投影 |
| ADR-0065 journal-as-truth | **增强**。新增 `projected_state` 字段，SSE 视图，jsonl 严格剥离 |
| ADR-0037 record-as-data | 不变。ToolInvoked 仍是事件事实账本 |
| ADR-0015 contracts-purity | **轻微违反**（待修复）。`lca/contracts/observability/schemas/v2.py:EnvelopeV2` 不是 `@dataclass`；pre-existing，待另起 ADR 治理 |

---

## 8. 验收规约

### 8.1 单元

```sh
uv run pytest --no-cov tests/tools/ -q
# 期望 ≥ 110 passed（contract + projection + reconciliation）
```

### 8.2 端到端契约

```sh
uv run pytest --no-cov tests/tools/test_render_contract_reconciliation.py -q
# 期望 68 passed：每个 Tool 在 REGISTRY、有 renderer、wire_key 是 camelCase
cd lobehub-ui && pnpm vitest run src/store/chat/agents/transports/lcaToolRender/projection.test.ts
# 期望 16 passed
```

### 8.3 SSE 回归

```sh
uv run pytest --no-cov tests/test_run_live_ui_sse.py tests/test_tool_event_facts.py -q
# 期望 21 passed（不得因 projected_state / output_text 字段新增回归）
```

### 8.4 不变量

```sh
# 1. SSOT 一致
uv run python -c "from lca.infrastructure.tools.contract import REGISTRY, render_registry_to_ts; ts = render_registry_to_ts(); import re; m = re.search(r'\\\"executeCode\\\"', ts); assert m, 'codegen must produce executeCode'"
# 2. jsonl 不带 projected_state
grep -l "projected_state" traces/runs/*/run.jsonl 2>/dev/null && echo "FAIL: jsonl leak" || echo "OK"
# 3. SSE 带 projected_state (manual via DevTools)
```

### 8.5 用户体验（前端手测）

| 场景 | 期望 |
|---|---|
| `activate_skill('officecli')` | header 显示 skill 名 + SKILL.md 正文 |
| `read_skill_reference` | 路径 + 文件内容高亮 |
| `executeCode` / `runCommand` | code 高亮 + stdout + stderr + 文件列表 |
| 流式 `SandboxOutputDelta` | ToolInvoked 落地后 stdout 不被擦 |

---

## 9. 后续 Task

| Task | 内容 |
|---|---|
| **Task 8** | 删 `lcaJournal.ts` 家族（lcaJournal.ts / lcaJournal.test.ts / .generated/lcaJournal.generated.ts / lcaWire.ts）；更新 `lca_run_driver.py` patch metadata 不再拷贝它们。LcaRunDriver 完全切到 `projectToolCall()`。 |
| **Task 9** | 后端给 `read_skill_reference` 补 `size` / `file_type` / `encoding`（现在缺这三个，renderer 早 return null） |
| **Task 10** | ENVELOPE_V2 ADR（治理 `EnvelopeV2` 不是 dataclass 的 ADR-0015 违规） |
