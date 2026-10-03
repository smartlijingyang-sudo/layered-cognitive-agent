# ADR-0279 — 意图-工具结构对账与 JIT 动态装配（Intent-Tool Structural Reconciliation & JIT Hydration）

## 状态

**Proposed — 2026-10-04**

> **一句话**：终结"用嘴干活不用手"（claim without doing）顽疾——在 `think.decision.parse` 与 `think.gate` 之间利用现有 `think.decision.repair` 节点建立意图-工具结构对账（`reasoning_tools - tool_calls ≠ ∅`），动态为当前 turn JIT 挂载缺失工具 Schema 并单次回环 Nudge 重试，消除对易碎动词表的依赖。

**Extends**：
- [ADR-0255](0255-muse-production-runtime-full-reference.md)（Muse 生产运行时全量参考）：本 ADR 是 Muse L0 原生常驻与 L1 按需加载之间的自愈桥梁——解决模型“想要手却不知道去拿工具”的脱节；
- [ADR-0256](0256-tool-namespace-taxonomy.md)（工具命名空间划分规范）：承接 Defer 加载协议，将原本只能由模型显式调用 `tool_search` 加载，扩充为支持 Runtime 意图驱动 JIT 自动注入；
- [ADR-0260](0260-forced-retrieval-and-write-before-claim.md)（强制检索与写盘铁律契约）：本 ADR 与 0260 的 `guard_reply` 形成“事前 JIT 预防纠正”与“事后落地严格否决”的双层防线。

**实证来源**：
2026-10-03 `run_a3e03da5a40a` 线上事故实测：
- 用户要求：“希望记住这个case 后面我们还得跟进这块”；
- 模型 Thinking：“用户希望我记住这个case……我需要用 memory_add 工具把这个case记录下来。”；
- 真实行为：因为 `memory` 命名空间处于 DEFERRED 状态，Wire 上只有 `core` 的 3 个工具，模型没有看到 `memory_add` 的 Schema；模型未主动调用 `tool_search(namespace='memory')`，直接发生幻觉在正文回复“记下了。我把这个 case 的关键信息和待跟进事项都记录下来……”，`tool_calls` 为空。
- 最终结果：虽然后端 ADR-0260 拦截并改写，但前端已通过 Stream 呈现虚假承诺，用户体验与信任受到严重损害。

---

## 0. 接任务前 7 问

1. **问题是什么？** 模型在思考链中明确判定需要执行动作（如“用 memory_add 记录”），但因对应工具未在 Wire 上且模型未自主调用 `tool_search`，模型退化为纯文本伪造完成（用嘴应付），导致意图与动作脱节。
2. **受影响的事实或契约是什么？** `think.subgraph` 内部回环路由、`think.decision.repair` 节点决策逻辑、`DeferPolicy` 配置、Spine 审计事件。
3. **唯一真值在哪里？** 结构对账的真值是**集合差**：`ToolManifest` 符号集合在 `reasoning` 中的命中子集与本轮 `Decision.tool_calls` 的差集，不依赖任何自然语言动词词表。
4. **改变哪个边界？** `think` 认知内部子图（`think.decision.repair` 的 `RoutingDecision` 改道回环），完全在认知闭环内部，不穿透到 `act` 执行平面，更不绕过 Gate。
5. **现有 Protocol / ADR 能否表达？** 不能。ADR-0256 仅支持模型显式 `tool_search`；ADR-0260 仅提供事后文本拒绝，没有认知阶段的 JIT 自愈能力。
6. **失败、重试、恢复和幂等语义是什么？**
   - 单轮上限：每 turn 最多允许 1 次 JIT 自动注入与 Nudge 重试（防死循环）；
   - 熔断降级：重试后若模型依然不调用工具，立即停止回环，跌回正常流程并由 ADR-0260 的 `guard_reply` 执行严格否决；
   - 范围收敛：仅对 `DeferPolicy.auto_hydrate_namespaces` 白名单内的命名空间触发。
7. **如何验证？**
   - 单元测试：构造包含 deferred 工具声明的 reasoning 且 tool_calls 为空的场景，验证触发 JIT 加载、Schema 进 Wire 且生成 Nudge；
   - 防循环测试：验证同一 turn 第二次触发时必须放行不回环；
   - 线上 Run 复验：断言未加载工具被意图唤醒后成功发起真实工具调用。

---

## 1. 核心契约

### C1 — 结构对账优于动词匹配（Structural Reconciliation）
- 弃用容易漏报与误杀的自然语言完成动词表（如“已保存/记下了/搞定”）；
- 采用确定性的符号结构对账：从本 run 的工具清单（`ToolManifest`）中提取已注册工具名，对模型 `reasoning` 进行严格精确匹配；
- 当且仅当满足下列条件时判定为 **Intent-Tool Mismatch**：
  $$\{t \in \text{DeferredTools} \mid t \text{ mentioned in reasoning}\} \setminus \{t \in \text{ActualToolCalls}\} \neq \emptyset$$
  且该工具所属的命名空间在 `auto_hydrate_namespaces` 白名单中，且当轮未曾进行过 JIT 注入。

### C2 — JIT 动态装配与 Think 微回环（JIT Hydration & Micro-Loop）
- 挂载点位于 `think.decision.parse` 之后、`think.gate` 之前（即现有的 `think.decision.repair` 节点）；
- 命中 Mismatch 时，`think.decision.repair` 执行：
  1. 动态将目标 namespace 标记为 `loaded_namespaces`，将其完整 Schema 动态合并入当轮 Wire Tools；
  2. 丢弃当前试图“用嘴应付”的纯文本回复（避免污染下游与流式）；
  3. 构造一条系统级精准引导（Nudge Prompt）：
     > `[System Guidance] 检测到你意图使用工具 '{tool_name}'，已为你动态加载其 Schema。请直接发起该工具调用，严禁仅以纯文本声称已完成。`
  4. 发出 `RoutingDecision(next_node="think.route.decide", next_hint="jit_hydrated")`，在当前 turn 内重走单次推理。

### C3 — 单轮单次防死循环硬顶（Max Hydration Cap）
- 单个 Turn 内 JIT 注入与回环次数严格限制为 **1 次**（`max_jit_hydrations_per_turn = 1`）；
- 若重调后模型仍未发起工具调用，不再次重试，直接放行给 `think.gate`，由 ADR-0260 的 `guard_reply` 作为最后防线将其改写为拒绝句。

### C4 — Per-tool Eager 下沉的互补协同
- 本机制与“高频只读工具下沉 Eager”（ADR-0256 补充）互为表里：
  - **静态常驻**：`memory` 全域 + `file` 只读域（`listFiles`, `readFile` 等）默认进 Eager，保证高频感知与检索 0 往返、0 延迟；
  - **动态兜底**：写操作与低频 deliberate 操作（`file` 写、`shell`、`ext`）保持 Deferred，一旦模型在思考中触碰，由本机制在当轮无感补上 Schema。

---

## 2. 架构落地设计

### 2.1 挂载位置与时序

```text
[think.history.assemble] 
        ↓
  [llm.invoke]  (流式输出 reasoning + text)
        ↓
[think.decision.parse] (输出初步 Decision)
        ↓
[think.decision.repair] ──[结构对账: 发现遗漏工具 X]──> (JIT 挂载 Schema + Nudge)
        │                                                     │
   [无 Mismatch]                                           [重试回环]
        │                                                     ↓
        ↓                                           [think.route.decide]
  [think.gate] (最终审批与控制)
```

### 2.2 核心实现伪代码

在 `lca/cognition/intent/reconciler.py`（纯函数，无状态）：

```python
@dataclass(frozen=True, slots=True)
class IntentReconciliationResult:
    mismatch_detected: bool
    missing_tools: tuple[str, ...] = ()
    missing_namespaces: tuple[str, ...] = ()
    nudge_message: str | None = None

def reconcile_intent(
    *,
    reasoning: str | None,
    tool_calls: Sequence[ToolCall],
    defer_session: ToolDeferSession | None,
    hydrated_count: int,
    allowed_namespaces: frozenset[str],
) -> IntentReconciliationResult:
    if hydrated_count >= 1 or not reasoning or not defer_session:
        return IntentReconciliationResult(mismatch_detected=False)

    called_names = {call.name for call in tool_calls}
    missing_tools = []
    missing_namespaces = set()

    for ns in defer_session.namespaces:
        if ns.name not in allowed_namespaces or ns.name in defer_session.loaded_namespaces:
            continue
        for tool_name in ns.tool_names:
            if tool_name in reasoning and tool_name not in called_names:
                missing_tools.append(tool_name)
                missing_namespaces.add(ns.name)

    if not missing_tools:
        return IntentReconciliationResult(mismatch_detected=False)

    nudge = (
        f"[System Notice] 检测到你意图使用工具 {missing_tools}，已为你实时加载对应 Schema。"
        f"请立即发起该工具调用，严禁以纯文本直接回复完成。"
    )
    return IntentReconciliationResult(
        mismatch_detected=True,
        missing_tools=tuple(missing_tools),
        missing_namespaces=tuple(missing_namespaces),
        nudge_message=nudge,
    )
```

---

## 3. 待拍板事项

1. **流式 Token 撤回/覆盖机制**：
   - LLM 生成时若已将部分草稿流给前端，微回环重试产生新的回复时，前端前端层如何优雅覆盖旧气泡？（建议在回环发生时下发 `stream.clear_draft` 控制事件）。
2. **Shell 等高危命名空间是否纳入自动 JIT**：
   - 倾向于纳入：工具 Schema 的可见性不等于执行权限，进入 Act 阶段仍会被 `ApprovalPolicyEngine`（ADR-0246/0256）硬拦截审批，无需在 Schema 阶段过度设防。

---

## 4. 验收用例

- **T1（结构对账命中与 Schema 注入）**：单测构造 `reasoning` 包含未加载工具名 `fileWrite` 且 `tool_calls` 为空，断言对账结果为真，对应 namespace 成功转入 `loaded_namespaces`，并生成特定 Nudge。
- **T2（单轮单次上限拦截）**：单测构造 `hydrated_count = 1` 时再次输入未调用的 reasoning，断言对账为假，直接放行，不发生二次重试。
- **T3（非白名单过滤）**：reasoning 提及未在 `auto_hydrate_namespaces` 中的工具，不触发回环。
- **T4（Spine 事件审计）**：回环发生时，Spine 轨迹中必须记录 `spine.intent.reconciled` 事件，包含缺失工具名、触发时间与装配结果。
