# ADR-0032: DelegationResult 一等公民 —— 路由账本、幂等委派与自描述 span

## 状态
Accepted

## 背景

routing 探针（真实 LLM，qwen-plus）出现两类病灶：

**行为病灶 —— 重复委派。** Lead 第 0 步并行委派 Alice/Bob 并拿到返回，第 1 步却
**再次委派相同任务**。模型 rationale 原文：「CONTEXT 中虽已给出 TOOL_RESULT，但该
结果属于历史执行记录…任务流程强制要求'必须先委派'——即需主动触发委派动作」。一次
冗余往返浪费约 38% 墙钟时间（21.4s → 理论 13.3s）与 3/7 次 LLM 调用。

根因链共四层：

1. **语义层**：成员返回在记忆边界丢失类型与归属。`DelegateOperation` 产出结构化
   `Observation(extra=OBS_MEMBER_RESULTS…)`，但 `SimpleMemorySystem.update` 一律压扁成
   `f"TOOL_RESULT: {payload}"`；监督者无法区分「我的委派已返回」与「某条历史记录」。
   成员自己的 respond 输出也被标成 TOOL_RESULT。
2. **状态层**：`RoutingState` 只有 `teammates/assigned_roles/notes`，`assigned_roles`
   是纯角色名软日志，不记录子任务与返回值。ADR-0028 刻意禁止 routing 挂结算 gate
   （正确），副作用是 routing 平面零结构化事实支撑「已经有人答过了」的判断。
3. **执行层**：委派边界无幂等性。工具路径有 SafeExecutor 缓存与 `ToolCall.idempotency_key`，
   委派路径无条件重跑。
4. **可观测层**：`llm.chat`/`tool.execute` 不带 `agent_role`/`step`；span 按完成顺序
   发射，flat 渲染器用「上一个 section」可变状态兜底 → 并发下 Bob 的 llm.chat 挂到
   Alice 分节（日志中实际发生）。

## 决定

### 1. `DelegationResult` 类型 + 路由账本（事实源）

`lca/contracts/delegation.py`：

```python
@dataclass(frozen=True)
class DelegationResult:
    result_id: str
    target_role: str
    subtask: str
    output: str | None
    success: bool
    error: str | None
    task_id: str | None
    step: int
    returned_at: datetime


def find_result(results, *, target_role, subtask) -> DelegationResult | None: ...
```

`RoutingState` 新增 `results: list[DelegationResult]`（`ROUTING_FIELD_WHITELIST` 同步）。
**账本是事实记录，不是结算 gate** —— routing 依旧没有 MustConsultAllMembers 不变量
（ADR-0028 的禁令保持原样）。contracts 放纯函数先例：`role_status_rules.py`（ADR-0025）。

### 2. 幂等委派（缓存语义，非门禁）

`DelegateOperation` 每个 spec 调度前查 `find_result(results, target_role, subtask)`，
命中成功结算则短路复用，发射 `SpanName.DELEGATE_CACHE_HIT` span，不产生 transport
往返。语义刻意保守：**仅拦截字面重复的 (角色, 子任务)**；改写措辞的新问题不受影响，
失败结算可重新委派。实现收敛在 `lca/layer1_cognitive/body/delegation_cache.py`。

consult/board 不引入账本 —— 其 MemberStatus gate 已拦终态角色（ADR-0025 问题 C 的
修复）；`find_result` 接口对其后续扩展保持可用。

### 3. 记忆记录类型化（`MemoryRecordKind`）

`MemoryRecord.kind: GENERIC | TOOL_RESULT | DELEGATION_RESULT | RESPONSE`（默认 GENERIC
向后兼容），归属进既有 `metadata`。`SimpleMemorySystem.update` 按 `Observation.extra`
的 `OBS_RESULT_KIND` 分派：委派结果**逐成员**写一条带 `role/subtask/step` 归属的记录；
工具结果保留 `TOOL_RESULT:` 前缀（MockLLM 解析兼容）；respond 记为 `RESPONSE`。
三个 Operation（respond/use_tool/delegate）在 act 边界为 Observation 打上 kind 标签。

### 4. 监督者 prompt：MEMBER_REPORTS 为唯一委派事实视图

routing_prompt 新增 `MEMBER_REPORTS` 段，由 `routing.results` 确定性渲染
（`- Alice | step 0 | 子任务: … | 已返回: …`；失败条目标注「可重新委派」）。
CONTEXT 中**排除** DELEGATION_RESULT 记忆记录 —— 同一事实不在 prompt 中出现两次
（双份表示正是本次模型误判的诱因）。规则改写为以 MEMBER_REPORTS 为准、禁止字面重复。

### 5. 自描述 span + 无状态渲染（对齐 OTel GenAI semconv）

- L0 遥测运行时新增 ambient actor（`set_actor(role, step)`，ContextVar，baggage 式），
  由 `SimpleHookRegistry.trigger` 在循环边界设置（`_loop` 零改动，AST≤30 门禁不受影响）；
  `_Span.__enter__` 对缺 `agent_role`/`step` 的 span 自动补齐，显式属性优先。
- `section_key_for_span` 变为纯属性推导，删除「沿用上一节」的可变状态兜底；
  并发成员交错完成时各行挂对角色节。
- 场景卡（run.plan 横幅）与实时 span 行渲染拆分为 `plan_narrative.py` /
  `run_narrative.py`（共享工具 `narrative_utils.py`），两文件均回到 250 行门禁内。

## 放弃的方案

- **给 routing 挂结算 gate**：违背 ADR-0028 的自由路由产品前提；账本+幂等在不引入
  不变量的前提下消除冗余。
- **模糊匹配去重（子任务相似度）**：引入不确定性与误伤；字面精确匹配零误判，
  语义级重复交给 prompt 事实视图解决。
- **仅改 prompt 措辞**：不改事实表示，模型仍可能误判；本次事故中 prompt 规则 4/5
  已存在但失效。

## 后果

- **正面**：同任务 LLM 调用 7→4、lead steps 3→2、时长 -38%；委派事实对模型确定性
  可见；flat 叙事并发正确；cache hit 在 trace/digest 可断言。
- **负面 / 迁移**：`RoutingState` 字段面变化（白名单已同步，
  `test_routing_whitelist` 守护）；记忆记录新增 `kind` 字段（默认值兼容）；
  `run_narrative` 拆分后，plan 相关函数改从 `plan_narrative` 导入。

## 与既有 ADR 的关系

- **Extends ADR-0028**：保留「routing 无结算 gate」，补上缺失的结果结构。
- **Extends ADR-0031**：span 属性完备性（ambient actor），闭集词汇新增
  `delegate.cache_hit`；双轨测试策略不变。
- **谱系 ADR-0025**：委派去重两条腿 —— consultation 用 gate，routing 用账本+幂等。
- **纪律 ADR-0026**：不改 `ConsultationState`（白名单不动）。
