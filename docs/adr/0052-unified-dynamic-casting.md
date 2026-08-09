# ADR-0052: Solo/Team 分治 —— 退役静态模式目录，solo 回归裸模型

## 状态

Proposed

## 背景

ADR-0042 引入了自动组队（`auto` 模式），验证了「LLM 选角 → 白名单校验 →
确定性编译」链路的可行性。但当前架构存在两个根本问题：

### 问题一：solo 被排除在动态机制之外

`CASTING_MIN_ROLES = 2` 把单人场景挡在 casting 白名单外面，solo 只能退回
`mode_catalog.py` 里写死的 `SOLO_ANALYST`（"独立分析师"）。这个写死角色
是一个虚假的差异化——用户不在乎 agent 叫"分析师"还是"顾问"，影响输出
质量的是模型自身的对齐训练，不是 role 字段的标签。

### 问题二：11 个概念 vs 业界 0 个概念

用户需要理解 routing/consult/board/pipeline/fan_out/peer_relay/peer_swarm/
debate/graph/solo + auto 这 11 个模式才能选对。而业界在 solo 场景的做法
是完全不暴露角色概念：

| 产品 | Solo 默认 agent | 角色概念 |
|---|---|---|
| LobeHub | `systemRole: ''` + `meta: {}` | 无 |
| ChatGPT | 无 system prompt | 无 |
| Claude | 无 system prompt | 无 |
| CrewAI | 用户显式指定（非默认） | 仅 team 场景 |

**LobeHub 源码实证**（`packages/const/src/settings/agent.ts` + `meta.ts`）：

```typescript
export const DEFAULT_AGENT_CONFIG: LobeAgentConfig = {
  systemRole: '',        // 空字符串 —— 不注入 system message
  // model, params, plugins, tts...
};
export const DEFAULT_AGENT_META: MetaData = {};  // 无 title/avatar/description
```

`SystemRoleInjector.buildSystemRoleContent()` 在 `systemRole` 为空时返回
`null`，跳过注入——agent 就是一个裸模型 + 参数 + 工具。

### 问题三：`run_executor.py` 的 if/else 分支

```python
if mode == AUTO_MODE_KEY:
    runnable = await build_runnable_auto(...)
else:
    runnable = build_runnable(mode, llm, observability=session.hub)
```

ADR-0042 显式登记为「已知妥协」。这个分支的本质是：两种根本不同的
构建机制（同步查表 vs 异步 casting）被迫共用一个入口。

## 决定

### 1. Solo：裸模型，零角色概念（对齐 LobeHub）

Solo 模式不引入任何角色设定。`build_solo_agent` 返回一个空 role/goal/
backstory 的 `Agent`：

```python
def build_solo_agent(
    llm: LLMAdapter,
    *,
    observability: str | ObservabilityBackend = OBSERVABILITY_CHOICE_CONSOLE,
) -> Agent:
    return Agent(
        role="",
        goal="",
        backstory="",
        tools=build_default_tools(),
        llm=llm,
        observability=observability,
    )
```

Prompt 渲染侧：`role` / `goal` / `backstory` 为空时不渲染对应 section。
这与 LobeHub 的 `SystemRoleInjector` 行为一致——空 systemRole 跳过注入。

**为什么不用写死的 `SOLO_ANALYST`**：角色标签对模型行为没有可测量的影响。
模型的对齐训练已经覆盖了通用助手能力。写死角色反而制造了虚假的差异化，
增加了维护成本（需要为这个写死角色写 backstory），且与业界做法不一致。

### 2. Team：保持 ADR-0042 的 LLM casting（不变）

Team 模式继续使用 `LLMTeamCaster.cast()` → 白名单校验 → `build_from_casting_plan()`。
`CASTING_MIN_ROLES = 2` 保持不变——casting 就是 team 的事，solo 不进入这条路径。

### 3. `mode_catalog.py`：从 10+1 模式收成 1 个 team 入口

**保留**：

```python
MODE_DEFINITIONS: Final[dict[str, ModeDefinition]] = {
    "team": ModeDefinition(
        key="team",
        help_text="团队 · 系统按任务自动组队和分工",
        has_lead=False,
        example_prompts=(...),
        member_roles=(),
    ),
}
```

**删除**：

- `TEAM_LEAD` / `TECH_ADVISOR` / `BUSINESS_ADVISOR` / `OPERATIONS_ADVISOR` /
  `SOLO_ANALYST` 五个 `AgentRoleTemplate`。
- `routing` / `consult` / `board` / `pipeline` / `fan_out` / `peer_relay` /
  `peer_swarm` / `debate` / `graph` / `solo` 十个 `ModeDefinition`。
- `AUTO_MODE_KEY` / `AUTO_MODE_HELP` / `AUTO_EXAMPLE_PROMPTS`——不再需要
  独立的 auto 入口，因为 team 就是 auto。
- `_MEMBER_MAX_STEPS` / `_LEAD_MAX_STEPS` / `_SOLO_MAX_STEPS` 和
  `max_steps_for_role`。

**`ModeDefinition` 简化**：删除 `lead_role` / `coordination` / `max_rounds`
字段，只保留 `key` / `help_text` / `example_prompts` / `member_roles`（空 tuple，
向后兼容字段访问）。

### 4. `run_executor.py`：语义分支，不是妥协分支

```python
if mode == "solo":
    runnable = build_solo_agent(llm, observability=session.hub)
else:
    runnable = await build_runnable_team(
        question,
        llm,
        observability=session.hub,
        trace_id=session.trace_id,
        run_id=session.run_id,
    )
```

这个 `if/else` 与 ADR-0042 的「已知妥协」本质不同：

| | ADR-0042 的 if/else | 本 ADR 的 if/else |
|---|---|---|
| 分支原因 | 同一种机制的同步/异步分界 | 两种根本不同的构建机制 |
| 语义 | 人为的（solo 本可以走 casting） | 自然的（solo 不需要 casting） |
| 未来扩展 | 「出现第二个特殊入口就重构」 | 分支稳定，不会增长 |

### 5. `team_factory.py`：`build_runnable` 退役

- 删除 `build_runnable`（同步查表路径）及 `_build_agent` / `_coordination_for` /
  `_build_linear_graph` 三个 helper。
- `build_runnable_auto` 重命名为 `build_runnable_team`，返回类型保持 `Team`。
- 删除 `AgentRoleTemplate` / `get_mode_definition` / `max_steps_for_role` 的
  import。

### 6. 前端 & 契约生成

- `scripts/generate_gateway_contracts.py` 从 `MODE_DEFINITIONS` 生成
  `web/src/contracts/modes.generated.ts`，现在只有 1 个 key（`team`）。
- `ModePicker` 从 11 张卡片收成 2 个入口——「直接问」（solo）/「组队做」
  （team）。solo 不需要卡片，可以是默认输入框的直接提交。
- ADR-0040 的契约生成机制不变，数据源从 10 套角色定义变成 1 个 key + 通用文案。

### 7. 测试守卫收敛

- `tests/harness/modes.py`：`_SCENARIOS` 从 10 个 key 收到 1 个（`team`）。
  Alice/Bob 剧本保留作为 team 场景的确定性探针。
- `tests/test_refactor_guards.py::TestModeCatalogKeyParity`：断言两侧 key
  集合相等——集合从 10 个收到 1 个，守卫逻辑不变。
- Solo 场景不需要 scripted LLM——它是确定性的裸模型调用，无选角不确定性。

## 已知妥协（显式登记，非遗忘）

1. **Solo 没有角色差异化**：对于某些高度专业化的任务（如法律文书分析），
   一个写死的 expert backstory 可能比裸模型更好。但这是内容优化问题，
   不是架构问题——未来可以通过 skill 激活（ADR-0048）或用户自定义 agent
   来解决，不需要在架构层预埋角色机制。
2. **`MODE_DEFINITIONS` 只剩 1 个 entry**：dict 结构看起来过度设计。保留
   dict 而非换成单值的好处是：前端契约生成脚本的字段访问路径不变
   （`definition.key` / `definition.help_text`），未来如果需要加回静态
   模式（如 "research" / "code" 预设），直接加 entry 即可。
3. **`build_runnable_team` 仍然需要一次 LLM casting 调用**：team 场景的
   延迟/成本不变。这是 ADR-0042 已登记的妥协，本 ADR 不改变。

## 分阶段路线

- **Phase 1（本 ADR 落地范围）**：
  - `build_solo_agent` 函数（裸模型）。
  - `mode_catalog.py` 从 10 模式收成 1 个 `team` 入口。
  - `run_executor.py` 的 if/else 改为语义分支（solo 同步 / team 异步 casting）。
  - `team_factory.py` 删除 `build_runnable`，`build_runnable_auto` 重命名为
    `build_runnable_team`。
  - 前端 `ModePicker` 收成 2 入口，契约生成脚本同步改。
  - 测试：`tests/harness/modes.py` 收到 1 个场景，守卫断言同步改。

- **Phase 2（后续 ADR）**：解锁 `graph` 治理。`CastingPlan` 增加图边描述，
  casting prompt 增加 graph 相关指令。与 ADR-0042 Phase 2 对齐。

- **Phase 3（后续 ADR，可选）**：参考 LobeHub Agent Builder，允许用户创建
  自定义 agent 配置（role/goal/backstory）并保存为预设。这是用户侧的定制
  能力，不影响框架层的 solo/team 分治。

## 后果

### 正面

- **用户需理解的概念从 11 个收到 0 个**：solo 不需要任何概念（直接问），
  team 只需要知道「可以组队」。与 LobeHub / ChatGPT / Claude 对齐。
- **Solo 零额外成本**：不需要 casting LLM 调用，不需要角色库，不需要
  白名单校验。延迟 = 0，成本 = 0。
- **`mode_catalog.py` 从 200+ 行收到 ~30 行**：删除 5 个硬编码模板、10 个
  静态 `ModeDefinition`、4 个 helper 函数、3 个 max_steps 常量。
- **`run_executor.py` 的分支语义正确**：不再是 ADR-0042 登记的「已知妥协」，
  而是两种根本不同机制的自然分界。
- **治理词表保留**：九词表（routing/consult/board/pipeline/fan_out/peer_relay/
  peer_swarm/debate/graph）本身不动，只是从「用户手动选」变成「系统按任务
  判断」。ADR-0030 的一元领域语言不受影响。

### 负面

- **Solo 失去角色差异化**：见已知妥协 #1。缓解：通过 skill 激活或用户
  自定义 agent 来解决，不需要架构层预埋。
- **迁移成本**：10 个 `example_prompts` 需要合并到 team 入口的 `example_prompts`
  里。前端 `ModePicker` 需要重新设计。

## 放弃的方案

1. **Solo 也走 casting（`CASTING_MIN_ROLES = 1`）**：每个 solo run 多一次
   LLM 调用的延迟/成本，且选出的角色标签对输出质量没有可测量的影响。
   不对称的问题不需要对称的解法。
2. **Solo 走 embedding 匹配选角色**：引入 embedding 模型依赖、增加延迟、
   需要维护匹配阈值。收益（一个角色标签）不值得这个复杂度。
3. **保留 10 个静态模式作为「高级选项」**：概念数还是 11，用户看到 11 个
   选项时的认知负担不会因为「推荐 auto」而消失。选择悖论。
4. **照抄 LobeHub Agent Builder 允许当场生成角色卡**：改动面太大（内容安全、
   白名单校验对象变化），留待 Phase 3。

## 相关

- Extends: ADR-0042（角色库与自动组队）——solo 退出 casting，team 保持
  不变。本 ADR 是 ADR-0042 的「分治」路线，而非「统一」路线。
- Supersedes: ADR-0040（gateway mode_catalog 契约）——mode_catalog 从
  「10 个静态模式的单一事实源」变成「1 个 team 入口的单一事实源」。生成
  机制不变，数据源简化。
- Keeps: ADR-0030（一元领域语言）——九词治理表不动。
- Keeps: ADR-0034（声明式 TeamSpec）——CastingPlan → TeamSpec 的编译路径
  不变。
- Keeps: ADR-0042 的白名单校验 / 纠正重试 / prompt injection 防线——全部
  保留在 team 路径。
- Aligns: LobeHub `DEFAULT_AGENT_CONFIG.systemRole = ''` —— solo 裸模型对齐
  业界标准。
