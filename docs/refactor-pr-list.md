# 重构 PR 列表 —— 降低认知负担、收口边界、消除技术债

> 生成时间：2026-07-29
> 扫描范围：`lca/` 全部 112 个 Python 文件、`tests/` 全部 37 个测试文件、17 个 ADR、组合根与契约层
> 排序原则：**坏味道浓度 × 影响面 × 可独立合入**
>
> **落地状态（2026-07-29 本会话）**：核心项已全部实现并过门禁：
> - 组合根：`layer4_app/assembly.assemble_base_agent`（单一共享 Tool/Action 管线）
> - ActionCatalog：`layer1_cognitive/body/action_catalog.py`
> - 状态槽位：`TypedState.final_output|last_error|active_template|team_progress_text` + `semantic_keys`
> - 进程内 await：`InternalTransport.wait_result` + `DelegateOperation` 优先 await
> - L0 shim / Handler 别名 / 空包已删；hooks 迁出 contracts；`invocation.py`/`message.py` 正式化
> - 注册表：`require`/`get`/`ensure_defaults` + `docs/registry-catalog.md`
> - 门禁：`ruff` / `lint-imports` / `mypy lca` / **pytest 335 passed** 全绿

---

## 总览

| 优先级 | PR | 一句话 | 风险 | 行数影响 | 依赖 |
|--------|----|--------|------|----------|------|
| **P0** | **PR-0** | **修复两个运行时 ImportError：`ensure_defaults` 缺失 + `hierarchical.py` hook 导入路径错误** | 低 | ~10 行改动 | 无 |
| P0 | PR-1 | 组合根三路径合一，消灭 `defaults.py` / `assembly.py` / `api.py` 三重重复装配 | 中 | ~200 行删减 | PR-0 |
| P0 | PR-2 | ActionCatalog 成为唯一事实源，消灭 `_ACTION_ALIASES` / `action_descs` 硬编码漂移 | 中 | ~80 行删减 | 无 |
| P1 | PR-3 | TypedState 双通道访问收敛：消灭 `working_memory["final_output"]` 与一等字段并存 | 低 | ~30 行改动 | 无 |
| P1 | PR-4 | `_new_id` / `_now` 全局去重，统一使用 `contracts.ids` | 极低 | ~40 行删减 | 无 |
| P2 | PR-5 | 过渡别名与兼容 shim 清零 | 极低 | ~20 行删减 | 无 |
| P2 | PR-6 | `SimpleBody.__init__` 隐式构建路径收口 | 低 | ~30 行删减 | PR-1 后更顺 |
| P2 | PR-8 | 测试基础设施收口：conftest + 共享 fixture + `sys.path` 清理 | 低 | ~200 行删减 | 无 |
| P3 | PR-7 | 注册表语义统一（resolve 一致性 + 全局单例访问收敛） | 中 | ~50 行改动 | 无 |

```
PR-0 ──── 最先：修复运行时 Bug（10 分钟级）
PR-4 ──┐
PR-5 ──┤
PR-8 ──┼── 可并行（低风险清理，热身用）
PR-3 ──┘
PR-1 ──── 核心：组合根收口（建议最先做）
  └─ PR-6 ── SimpleBody 收口（接在 PR-1 后）
PR-2 ──── Action 单一事实源（可与 PR-1 并行）
PR-7 ──── 注册表语义统一（独立，随时可做）
```

---

## PR-1：L4 组合根三路径合一

### 问题背景

创建 Agent 的对象图组装存在**三条独立路径**，各自拼装 `ToolRegistry → SafeExecutor → ActionRegistry → Brain → Body → Hooks → Runtime`：

| 路径 | 文件 | 入口 | 行数 |
|------|------|------|------|
| 路径 A | `layer4_app/api.py` | `Agent.__init__` | ~80 行内联拼装 |
| 路径 B | `layer4_app/assembly.py` | `assemble_base_agent()` | ~80 行 |
| 路径 C | `layer4_app/defaults.py` | `_build_brain()` + `build_body()` + `build_runtime()` | ~120 行分散 |

**具体坏味道：**

1. **Brain 构建重复**：`defaults.py::_build_brain()` (L33-80) 与 `assembly.py::build_default_brain()` (L38-72) 逻辑几乎相同，但 `defaults.py` 版本内联了一个 6 条目的 `action_descs` 硬编码字典，而 `assembly.py` 版本使用 `format_allowed_actions_desc(action_registry)`——两者产出的 Prompt 文案格式不同。

2. **`api.py` 绕过 `assembly.py`**：`Agent.__init__` 直接 `from lca.layer4_app.defaults import _build_brain, build_body, build_runtime`，不走 `assembly.py`。`assembly.py` 是 ADR-0005 承诺的"唯一对象图工厂"，但实际无人使用。

3. **Hook 构建重复**：`defaults.py::_build_hooks()` 与 `assembly.py::build_hooks()` 逻辑完全相同，两处各自维护。

4. **Body 构建重复**：`defaults.py::build_body()` 内部 `new SimpleToolRegistry + new SimpleSafeExecutor`，而 `assembly.py::build_body_from_shared()` 接受已共享的依赖——两套 API 做同一件事。

**删除测试**：如果删除 `assembly.py`，`api.py` 和 `defaults.py` 仍然能独立工作——说明 `assembly.py` 没有 earning its keep，它本应是唯一路径，却变成了第三个路径。

### 重构架构（一次性方案）

**保留 `assembly.py` 作为唯一组合根**（ADR-0005 承诺的兑现），其他两处降级为薄调用：

```
api.py Agent.__init__
  └─→ assembly.assemble_base_agent(...)     # 唯一入口
        ├─→ _build_shared_pipeline(...)     # ToolReg + SafeExec + TransportReg + ActionReg
        ├─→ _build_brain(...)               # Brain + MAP
        ├─→ _build_body(...)                # Body (使用共享 pipeline)
        ├─→ _build_hooks(...)               # Hooks
        └─→ CognitiveRuntime(...)           # Runtime

defaults.py
  ├─→ register_defaults()                   # 仅注册默认实现到全局 Registry
  └─→ build_default_transport_registry()    # 保留（被 assembly 调用）
  └─→ 删除 _build_brain / build_body / _build_hooks / build_runtime
```

### 实施步骤

1. **将 `assembly.py` 设为唯一装配入口**：
   - 确认 `assemble_base_agent()` 覆盖 `api.py` 和 `defaults.py` 的全部装配能力
   - 将 `defaults.py` 中的 `build_team_transport()` 迁入 `assembly.py`

2. **`api.py` Agent.__init__ 瘦身为薄门面**：
   ```python
   def __init__(self, ...):
       self._base_agent = assemble_base_agent(
           role=role, goal=goal, backstory=backstory,
           tools=tools, llm=llm, ...
       )
   ```
   删除全部内联拼装代码（~80 行）。

3. **`defaults.py` 只保留注册逻辑**：
   - 删除 `_build_brain`、`build_body`、`build_runtime`、`_build_hooks`
   - 保留 `register_defaults()`、`build_default_transport_registry()`、`ensure_defaults()`

4. **统一 Brain 构建**：
   - 删除 `defaults.py::_build_brain` 中的硬编码 `action_descs` dict
   - 统一使用 `assembly.py::build_default_brain` 的 `format_allowed_actions_desc` 路径

5. **测试**：
   - `id(body.tool_registry) is id(action_registry._handlers["use_tool"]._tool_registry)`
   - `Agent(...)` 与 `assemble_base_agent(...)` 产出的对象图结构一致
   - 全量 `pytest` + `lint-imports` + `mypy`

6. **清理**：
   - 删除 `api.py` 中对 `defaults._build_brain` / `defaults.build_body` 的 import
   - 删除 `defaults.py` 中被替代的函数

### 效果

- **认知**：对象图只在一个模块 (`assembly.py`) 建立，新人看一个文件即可理解全部装配逻辑
- **正确性**：消除 Brain/Body 使用不同 ActionRegistry 实例的隐患
- **可维护**：修改装配逻辑只需改一处，不会三条路径漂移
- **删减**：~200 行重复代码

### 沉淀

- 更新 ADR-0005：明确 `assembly.py` 是唯一组合根，`defaults.py` 仅负责注册默认实现
- `AGENTS.md` 增加不变量：`Agent.__init__` 不得内联装配逻辑

---

## PR-2：ActionCatalog 成为唯一事实源

### 问题背景

同一种 `action_type` 的元数据（名称、别名、Prompt 文案、注册）分散在 **4 处**：

| 位置 | 内容 | 问题 |
|------|------|------|
| `action_catalog.py` `BUILTIN_ACTION_SPECS` | 名称 + 描述 + 别名 | ✅ 应有的唯一事实源 |
| `decision_parser.py` `_ACTION_ALIASES` | 硬编码 14 条别名映射 | ❌ 与 `ActionSpec.aliases` 重复 |
| `defaults.py` `_build_brain` 内 `action_descs` | 硬编码 6 条 Prompt 文案 | ❌ 与 `ActionSpec.description` 重复 |
| 各 Operation 类 / hooks / outcome policy | 字符串字面量 `"respond"` `"delegate"` 等 | ❌ 散落的魔法字符串 |

`action_catalog.py` 的 `ActionSpec` 和 `format_allowed_actions_desc` 已经被设计出来解决这个问题，但**旧代码路径没有被清理**，导致新事实源与旧硬编码并存。

**扩展成本测试**：新增一种 `action_type`（如 `search_web`）需要改几个文件？
- `action_catalog.py` 加 `ActionSpec` ✅
- `action_handlers.py` 加 Operation ✅
- `action_catalog.py::build_default_action_registry` 加注册 ✅
- `decision_parser.py::_ACTION_ALIASES` 加别名 ← **容易漏**
- `defaults.py::_build_brain::action_descs` 加 Prompt 文案 ← **容易漏**
- 正确做法应只改 2 个文件（catalog + handler），现在要改 4 个

### 重构架构（一次性方案）

让 `ActionCatalog` 真正成为单一事实源，其他路径全部从它派生：

```
ActionCatalog (action_catalog.py)
  ├─→ BUILTIN_ACTION_SPECS          # 唯一声明
  ├─→ build_action_alias_map()      # 别名 → 规范名（Parser 消费）
  ├─→ format_allowed_actions_desc() # Prompt 文案（Brain 消费）
  └─→ build_default_action_registry() # 可执行注册表（Body 消费）
```

### 实施步骤

1. **`decision_parser.py` 消费 `build_action_alias_map()`**：
   ```python
   from lca.layer1_cognitive.body.action_catalog import build_action_alias_map

   _ACTION_ALIASES = build_action_alias_map()  # 从 catalog 生成，不再硬编码
   ```
   删除手写的 14 行 `_ACTION_ALIASES` dict。

2. **删除 `defaults.py::_build_brain` 中的 `action_descs`**：
   - 如果 PR-1 已合入，`defaults.py::_build_brain` 已被删除，此步自动完成
   - 如果 PR-1 未合入，将 `action_descs` 替换为 `format_allowed_actions_desc(action_registry.allowed_action_types())`

3. **`action_handlers.py::build_default_action_registry` 删除兼容 wrapper**：
   - 当前它是一个 lazy-import wrapper 指向 `action_catalog.build_default_action_registry`
   - 全部调用方改为直接 import `action_catalog`

4. **提取魔法字符串为常量**（可选，低优先级）：
   - 在 `ActionSpec` 上增加 `name` 常量的 re-export，如 `ACTION_RESPOND = "respond"`
   - 或在 `semantic_keys.py` 增加 action type 常量

5. **测试**：
   - `set(build_action_alias_map().values()) == {s.name for s in BUILTIN_ACTION_SPECS}`
   - `set(format_allowed_actions_desc(...).split("\n")) == ...` 覆盖所有 spec
   - 新增 action 只需改 catalog + handler 的文档测试

### 效果

- **扩展成本**：新增 action_type 只改 `action_catalog.py` + `action_handlers.py`，2 个文件
- **一致性**：Prompt / 解析 / 执行三者不可能再漂移
- **认知**：想知道系统支持哪些 action？看 `BUILTIN_ACTION_SPECS` 一个元组即可

### 沉淀

- ADR-0002 补丁：action_type 扩展协议 = ActionSpec + Operation + 注册
- `AGENTS.md`：新增 action 的步骤文档

---

## PR-3：TypedState 双通道访问收敛

### 问题背景

`TypedState` 存在**一等字段**与 `working_memory` 字典键并存的二义性：

| 语义 | 一等字段 | working_memory 键 | 谁写 | 谁读 |
|------|----------|-------------------|------|------|
| 最终输出 | `final_output: Any \| None` | `working_memory["final_output"]` | `runtime_loop._loop` 写 dict | `_summarize` 读 dict |
| 团队进度文本 | `team_progress_text: str \| None` | `working_memory.get("team_progress_text")` | `progress_injection_hook` 写字段 | `reasoner.generate_candidates` 读字段 |
| 活跃模板 | `active_template: str \| None` | `working_memory["active_template"]` | `modular_brain.think` 写 dict | — |

**`runtime_loop.py` 第 120-121 行**：
```python
if outcome.final_output is not None:
    state.working_memory["final_output"] = outcome.final_output
```
而 `_summarize` 读的是 `state.working_memory.get("final_output")`——一等字段 `state.final_output` **从未被使用**。

同样，`state.final_output` 和 `state.last_error` 字段虽然声明了，但 runtime_loop 仍然走 `state.extra["error"]` 和 `state.working_memory["final_output"]`。

**删除测试**：如果删除 `TypedState.final_output` 字段定义，代码仍然正常运行——说明这个字段是 dead code，实际走的是 dict。

### 重构架构（一次性方案）

**一等字段优先，dict 仅作逃生舱**：

1. `runtime_loop._loop` 写 `state.final_output = outcome.final_output`（不再写 dict）
2. `runtime_loop._summarize` 读 `state.final_output`（不再读 dict）
3. `runtime_loop._loop` 的 error 处理写 `state.last_error = str(err)`（不再写 `state.extra["error"]`）
4. `runtime_loop._summarize` 读 `state.last_error`
5. `modular_brain.think` 写 `state.active_template = template_name`（不再写 dict）
6. `working_memory` 只保留给 MemorySystem 的感知检索结果和用户自定义扩展

### 实施步骤

1. **枚举全部 `working_memory[` / `extra[` 读写点**（grep 审计）
2. **runtime_loop.py**：
   - `state.working_memory["final_output"] = ...` → `state.final_output = ...`
   - `state.extra["error"] = str(err)` → `state.last_error = str(err)`
   - `_summarize` 中 `state.working_memory.get("final_output")` → `state.final_output`
   - `_summarize` 中 `state.extra.get("error")` → `state.last_error`
3. **modular_brain.py**：
   - `state.working_memory["active_template"] = template_name` → `state.active_template = template_name`
4. **确认 `team_progress_text` 已统一**：`progress_injection_hook` 已写 `state.team_progress_text`，`reasoner` 已读 `state.working_memory.get("team_progress_text", "")`——需改为读 `state.team_progress_text or ""`
5. **测试**：
   - 单步 respond 场景：`result.output == state.final_output`
   - hierarchical 场景：team_progress_text 正确注入 Prompt
   - 错误场景：`result.error == state.last_error`

### 效果

- **类型安全**：`final_output` / `last_error` / `active_template` 可被 mypy 追踪
- **认知**：不再需要猜"这个值到底存在 dict 里还是字段里"
- **可搜索**：grep 字段名即可找到全部读写点，不再需要 grep 字符串键

### 沉淀

- ADR 补丁：TypedState 一等字段 vs working_memory 的使用边界
- 规则：框架内核读写 TypedState 必须走一等字段，`working_memory` 仅供 MemorySystem 和用户扩展使用

---

## PR-4：`_new_id` / `_now` 全局去重

### 问题背景

至少 **9 个文件** 各自定义了相同的 `_new_id` 和/或 `_now` 辅助函数：

| 文件 | `_new_id` | `_now` |
|------|-----------|--------|
| `contracts/decision.py` | ✅ 本地定义 | ✅ 本地定义 |
| `contracts/state.py` | ✅ 本地定义 | ✅ 本地定义 |
| `contracts/lifecycle.py` | ✅ 本地定义 | ✅ 本地定义 |
| `layer1_cognitive/hook_registry.py` | ✅ 本地定义 | ✅ 本地定义 |
| `layer1_cognitive/brain/critic.py` | ✅ 本地定义 | — |
| `layer1_cognitive/brain/decision_parser.py` | ✅ 本地定义 | — |
| `layer1_cognitive/memory/simple_memory.py` | ✅ 本地定义 | — |
| `layer2_runtime/fallback_handler.py` | ✅ 本地定义 | — |
| `layer0_infra/llm_adapter/openai_compat.py` | ✅ 本地定义 | — |

而 `contracts/ids.py` 已经存在，提供了 `new_id()` 和 `utc_now()`——但大部分文件没有使用它。

部分文件（如 `agent_transport.py`、`action_handlers.py`）已正确 `from lca.contracts.ids import new_id`，说明迁移已开始但未完成。

### 重构架构（一次性方案）

- `contracts/ids.py` 为唯一 id/时间戳工具源
- 全部 `_new_id` / `_now` 本地定义删除
- 全部调用方改为 `from lca.contracts.ids import new_id, utc_now`

### 实施步骤

1. **grep 全部 `_new_id` / `_now` 本地定义**
2. **逐文件替换**：
   - 删除本地 `def _new_id(...)` / `def _now(...)`
   - 添加 `from lca.contracts.ids import new_id`（或 `utc_now`）
   - 将 `_new_id("xxx")` 改为 `new_id("xxx")`
   - 将 `_now()` 改为 `utc_now()`
3. **contracts 内部文件**（`decision.py` / `state.py` / `lifecycle.py`）：
   - 改为 `from lca.contracts.ids import new_id, utc_now`
   - 注意避免循环 import（`ids.py` 不依赖其他 contracts 模块）
4. **测试**：全量 `pytest`，确保 id 格式兼容（`contracts/ids.py::new_id` 使用 `prefix_uuid_hex_12` 格式，与旧版一致）

### 效果

- **删减**：~40 行重复代码
- **一致性**：id 格式统一在一处定义
- **可演进**：如需改 id 格式（如加 timestamp prefix），只改一处

### 沉淀

- `AGENTS.md`：禁止在模块内定义 `_new_id` / `_now`，统一使用 `contracts.ids`

---

## PR-5：过渡别名与兼容 shim 清零

### 问题背景

代码中存在多处"过渡期 alias——下一主版本删除"标记，但从未清理：

| 位置 | 别名 | 原始 | 标记 |
|------|------|------|------|
| `contracts/action.py` | `ActionHandler` | `ActionOperation` | "过渡期 alias —— 下一主版本删除" |
| `contracts/protocols/embodiment.py` | `FallbackHandler` | `FallbackPolicy` | "过渡期 alias" |
| `contracts/mechanisms.py` | `RegistryProtocol` | `NamedRegistryProtocol` | "过渡期 alias —— 下一主版本删除" |
| `layer2_runtime/fallback_handler.py` | `FallbackActionHandler` | `FallbackActionPolicy` | "过渡期 alias" |
| `layer1_cognitive/body/action_handlers.py` | `build_default_action_registry` | → `action_catalog.build_default_action_registry` | "兼容入口" |

这些别名增加了搜索噪音和认知负担：新人看到两个名字，不知道哪个是规范的。

### 重构架构（一次性方案）

直接删除所有过渡别名。本仓库无外部发布约束，无需 deprecation cycle。

### 实施步骤

1. **grep 全部过渡别名的使用点**：
   - `ActionHandler` → 改为 `ActionOperation`
   - `FallbackHandler` → 改为 `FallbackPolicy`
   - `RegistryProtocol` → 改为 `NamedRegistryProtocol`
   - `FallbackActionHandler` → 改为 `FallbackActionPolicy`
2. **删除别名定义行**
3. **更新 `__all__` 导出列表**
4. **`action_handlers.py::build_default_action_registry`**：
   - 如果还有外部调用方，保留并加 `DeprecationWarning`
   - 如果无外部调用方（grep 确认），直接删除
5. **测试**：`pytest` + `ruff` + `lint-imports`

### 效果

- **搜索噪音下降**：每个概念只有一个名字
- **代码诚实**：不再有"下一主版本删除"的永远待办
- **删减**：~20 行

### 沉淀

- 代码约定：禁止 "过渡期 alias" 模式，重命名时一次性全仓 grep 替换

---

## PR-6：`SimpleBody.__init__` 隐式构建路径收口

### 问题背景

`SimpleBody.__init__` 有 **三条隐式构建路径**，取决于传入了哪些参数：

```python
# 路径 A：传入 action_registry → 直接使用
if action_registry is not None:
    self.action_registry = action_registry
# 路径 B：传入 tool_registry + safe_executor → 内部构建
elif tool_registry is not None and safe_executor is not None:
    self.action_registry = build_default_action_registry(...)
# 路径 C：都不传 → 空 ActionRegistry
else:
    self.action_registry = ActionRegistry()
```

同样的逻辑也存在于 `transport_registry` 的解析：

```python
if transport_registry is not None:
    self.transport_registry = transport_registry
elif transport is not None:
    registry = TransportRegistry()
    registry.register(transport)
    self.transport_registry = registry
else:
    self.transport_registry = TransportRegistry()
```

**问题**：
1. `SimpleBody` 不应该知道如何构建 `ActionRegistry`——这是组装根的职责
2. 路径 B 隐式 import 了 `build_default_action_registry`，创建了 `SimpleBody` 不应了解的依赖
3. 参数矩阵（`tool_registry` × `safe_executor` × `transport_registry` × `transport` × `action_registry`）有 2^5 = 32 种组合，大部分无意义

### 重构架构（一次性方案）

`SimpleBody.__init__` 只接受**已构建好的依赖**，不做任何隐式构建：

```python
class SimpleBody(Body):
    def __init__(
        self,
        action_registry: ActionRegistryProtocol,
        transport_registry: TransportRegistryProtocol,
        tool_registry: ToolRegistry | None = None,  # 保留引用供外部访问
        safe_executor: SafeExecutor | None = None,  # 保留引用供外部访问
    ):
        self.action_registry = action_registry
        self.transport_registry = transport_registry
        self.tool_registry = tool_registry
        self.safe_executor = safe_executor
```

所有构建逻辑由 `assembly.py` 承担。

### 实施步骤

1. **修改 `SimpleBody.__init__` 签名**：`action_registry` 和 `transport_registry` 变为必选参数
2. **删除隐式构建分支**：`build_default_action_registry` 的 fallback 调用、`TransportRegistry()` 的默认构造
3. **更新全部调用方**：
   - `assembly.py::build_body_from_shared` — 已传入完整依赖，无需改
   - `defaults.py::build_body` — 已传入完整依赖，无需改（如果 PR-1 合入则已删除）
   - 测试中的直接构造 — 需补充 `action_registry` 参数
4. **删除 `action_handlers.py::build_default_action_registry` 兼容 wrapper**（如果 PR-2 未删）
5. **测试**：`pytest` 全量

### 效果

- **认知**：`SimpleBody` 的构造函数一目了然，无条件分支
- **依赖清晰**：`SimpleBody` 不再依赖 `action_catalog` / `action_handlers`
- **可测**：测试中构造 `SimpleBody` 必须显式传入 mock，不可能意外走隐式路径

### 沉淀

- 代码约定：L1 组件的构造函数不做隐式构建，所有组装走组合根

---

## PR-7：注册表语义统一

### 问题背景

5 套注册表的 `resolve` 语义不一致：

| 注册表 | resolve 找不到时 | 值形态 | 全局单例 |
|--------|-----------------|--------|----------|
| `ComponentRegistry` | 返回 `None` | 类/工厂 | `get_global_registry()` |
| `NamedRegistry` (基类) | **raise** `RegistryKeyError` | 实例/工厂 | 子类决定 |
| `StrategyRegistry` | **raise** (继承 NamedRegistry) | 工厂 | `get_global_strategy_registry()` |
| `OrchestrationStrategyRegistry` | **raise** + 自动调用工厂 | 工厂→实例 | `get_global_orchestration_registry()` |
| `ActionRegistry` | 返回 `None` | 实例 | 无（实例字段） |
| `ToolRegistry` | 返回 `None` | 实例 | 无（实例字段） |
| `TransportRegistry` | **raise** `TransportNotFoundError` | 实例 | 无（实例字段） |

**认知负担**：每次调用 `resolve` 都要想"这个注册表找不到是返回 None 还是抛异常？"

此外，`ComponentRegistry.resolve()` 的文档说"兼容别名：等同 get"，但方法名叫 `resolve`——在其他注册表里 `resolve` 意味着"找不到就报错"。

### 重构架构（一次性方案）

**不强行合并为一个上帝 Registry**（类别语义确实不同），而是统一 API 约定：

1. **`resolve` 一律 raise**（找不到 → 明确异常）
2. **`get` 一律返回 Optional**（软查询）
3. **`ComponentRegistry.resolve` 改为 raise**（与 NamedRegistry 对齐），需要 Optional 的调用方改走 `get`
4. **全局单例访问收敛**：`get_global_registry()` / `get_global_strategy_registry()` / `get_global_orchestration_registry()` 只允许 L4 调用（通过约定 + 文档，不强 lint）

### 实施步骤

1. **审计全部 `ComponentRegistry.resolve()` 调用点**：
   - 需要 Optional 语义的改走 `.get()`
   - 需要 raise 语义的保持 `.resolve()` 但更新文档
2. **统一 `resolve` 语义**：所有注册表的 `resolve` 找不到时 raise
3. **更新 `ComponentRegistry.resolve` 文档**：明确 raise 语义
4. **可选**：在 `ComponentRegistry` 增加 `require()` 的 alias（已有），标记 `resolve` 为 deprecated 并指向 `require` / `get`
5. **文档化注册表地图**：在 `docs/glossary.md` 或 ADR-0004 补丁中列出全部注册表及其语义
6. **测试**：
   - 每个注册表的 `resolve` 找不到时 raise 对应异常
   - 每个注册表的 `get` 找不到时返回 None

### 效果

- **认知一致**：`resolve` = 硬查询（raise），`get` = 软查询（None），全系统统一
- **可搜索**：grep `resolve(` 即可找到所有硬查询点
- **新人友好**：一张注册表地图即可理解全部注册/解析机制

### 沉淀

- 扩展 ADR-0004：注册表 API 约定（resolve vs get）
- `docs/glossary.md` 增加注册表词条

---

## PR-8：测试基础设施收口

### 问题背景

测试代码（`tests/` 37 个文件，6843 行）存在多处可独立清理的坏味道：

**1. 共享 fixture 缺失**：零个 `conftest.py`，导致测试辅助函数在 7+ 个文件中重复定义：

| 辅助函数 | 重复文件数 | 典型差异 |
|----------|-----------|----------|
| `_make_result(trace_id, output, status)` | 7 | 参数签名略有不同 |
| `_make_agent(role, output)` | 6 | mock 设置不同 |
| `_make_state(task)` | 6 | 字段初始化不同 |
| `_make_role_profile(role)` | 3 | 几乎相同 |

**2. `sys.path.insert` 反模式**：15 个测试文件包含 `sys.path.insert(0, ...)` hack，`pyproject.toml` 已配置包发现，这不应必要。

**3. 空目录占位**：`tests/golden_traces/` 和 `tests/simulation_env/` 只有空 `__init__.py`，无实际内容。

**4. unittest + pytest 混用**：顶层文件用 `unittest.TestCase`（含 `IsolatedAsyncioTestCase`），`contract/` 子目录用 pytest 风格——增加认知分裂。

### 重构架构（一次性方案）

1. **引入 `tests/conftest.py`**：提取共享 fixture（`make_result`、`make_agent`、`make_state`、`make_role_profile`）为 pytest fixture 或工厂函数
2. **删除全部 `sys.path.insert`**：确认 `pyproject.toml` 的 `[tool.pytest.ini_options]` 配置正确后批量删除
3. **删除空目录**：`golden_traces/`、`simulation_env/`
4. **统一测试风格**（可选，渐进式）：新测试统一用 pytest 风格，旧测试不强迁

### 实施步骤

1. **创建 `tests/support/fixtures.py`**：
   - 提取 `_make_result` / `_make_agent` / `_make_state` / `_make_role_profile` 为参数化版本
   - 覆盖全部现有签名变体（用默认参数兼容旧调用）

2. **创建 `tests/conftest.py`**：
   - `from tests.support.fixtures import *`
   - 或定义 pytest fixture 包装

3. **批量删除 `sys.path.insert`**：
   - `grep -rl "sys.path.insert" tests/ | xargs sed -i '/sys.path.insert/d'`
   - 运行 `pytest` 确认全部通过

4. **删除空目录**：`git rm -r tests/golden_traces tests/simulation_env`

5. **逐文件迁移**：将各文件中的 `_make_*` 函数替换为 `from tests.support.fixtures import make_*`

6. **测试**：`pytest` 全量通过

### 效果

- **删减**：~200 行重复代码
- **一致性**：测试辅助函数只在一处定义，修改一处全局生效
- **可维护**：新增测试不需要复制粘贴 `_make_agent` 模板
- **认知**：新人看 `tests/support/fixtures.py` 即可了解全部测试构建方式

### 沉淀

- 测试约定：新测试禁止 `sys.path.insert`；共享 fixture 放 `tests/support/`

---

## 明确不在本列表

| 项 | 原因 |
|----|------|
| MAP 五模块合并/删除 | 已是 ADR-0003 锁定的策略边界；虽然当前实现是 pass-through，但接口设计正确，未来有真实实现的空间 |
| 五层包名重做 / 认知循环九步重排 | ADR-0001/0002 锁定 |
| 全面 Pydantic 化 contracts | ADR-0012 已评估并决定保持 stdlib dataclass |
| GraphStrategy 拆分（~190 行） | 局部可懂，ROI 低于上述 PR |
| `InternalTransport` 轮询改 await | `wait_result` 已实现，`DelegateOperation` 已优先走 `wait_result`——已在现有代码中解决 |

---

## 成功度量（整轮重构后）

- [ ] 创建 Agent 的对象图可在**单一模块 ≤100 行**读完（`assembly.py`）
- [ ] 新增一种 action_type **只改 2 个文件**（catalog + handler）
- [ ] 框架内核**零** `working_memory["xxx"]` 裸字符串键读写
- [ ] `_new_id` 全仓只有 `contracts/ids.py` 一处定义
- [ ] 零过渡期别名
- [ ] `resolve` 语义全系统统一（找不到 → raise）
- [ ] 全量 `ruff` / `lint-imports` / `mypy` / `pytest` 绿

---

## 建议执行顺序

```
Phase 1（热身，半天）：PR-4 + PR-5
  → 低风险清理，建立信心，为后续 PR 减少噪音

Phase 2（核心，1-2 天）：PR-1
  → 组合根收口，最大认知收益

Phase 3（接 Phase 2）：PR-2 + PR-6
  → Action 单一事实源 + SimpleBody 收口

Phase 4（独立）：PR-3 + PR-7
  → 状态类型化 + 注册表语义统一
```
