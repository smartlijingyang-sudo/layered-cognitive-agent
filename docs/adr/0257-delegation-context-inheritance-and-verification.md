# ADR-0257 — 委派上下文继承与复核协议：子 Agent 开局即有"我是谁"，回灌结果要做尽调

## 状态

**Proposed — 2026-10-01**

> **一句话**：终结"成员只收到一句话任务"的委派退化现状——委派信封 = standing 全量 + 父 turn 摘要 + 任务相关记忆投影，让子 agent 开局即拥有与父相同的"我是谁/用户是谁"；成员回灌只收 evidence 指针不收断言，父做与自己动手同等的尽调，不可逆失败先验实际效果再决定重试。

**Extends**：
- [ADR-0255](0255-muse-production-runtime-full-reference.md) §4.6（Subagent 上下文继承）：本 ADR 是 0255 §4.6 在 LCA 委派体系里的落地提案——0255 记录了"子 agent 继承完整父 transcript、父对回灌做尽调、不可逆失败先验效果"三条机制，本 ADR 回答"LCA 的接力式委派（task 字符串 + workspace handoff）怎么对齐这三条、以及全量 transcript 还是投影的取舍"；
- 不 supersede：ADR-0034（closed team 策略）、ADR-0037（journal as truth）、ADR-0187（assistant-agent）、ADR-0250（peer handoff bus）。

**实证来源**：`lca/agent/member_invoke.py`（89 行）+ `lca/agent/team_handle.py`（157 行）实现审计，2026-10-01。

---

## 0. 接任务前 7 问

1. **问题是什么？** `TransportMemberInvoker.invoke` 只发 `task` 字符串（pipeline 模式下再拼一个 workspace handoff block）；被调用的成员（peer/assistant/team member）开局**没有父的任何上下文**——不知道自己是被谁委派、用户是谁、父 turn 里已确认的事实是什么。成员只能靠调用者在 task 文本里"写全"，写不全就漂移。
2. **受影响的事实或契约是什么？** 委派信封的内容契约（`MemberInvoker.invoke` 的输入）、`DelegationIssued/Completed` 委派叙事的事件 payload、回灌 `Result.from_observation` 的信任等级、不可逆工具调用的重试策略。
3. **唯一真值在哪里？** 委派上下文的真值：本 ADR §3 的 `DelegationEnvelope` 定义；回灌复核的真值：journal 里的 `DelegationCompleted` 事件 + 本 ADR §4。
4. **改变哪个边界？**
   - 契约层：`MemberInvoker.invoke(member, task)` 的第二个参数从"裸 task 字符串"升级为"信封"（task + 父上下文投影），或新增 `invoke_with_envelope`；
   - 运行时层：`invoke_members_sequential` 在组装 `current_task` 时自动拼信封，不再依赖调用者手工在 task 里写背景；
   - 信任层：`Result.from_observation` 明确为"不可信输入"，父转正前须经 §4 复核。
5. **现有 Protocol / ADR 能否表达？** 不能。ADR-0034 只规定了成员调用通道与组合期 fail-fast；ADR-0037 把 journal 记为真值但没规定"委派出去的子上下文长什么样"；ADR-0250 的 handoff bus 是 peer 间的，不覆盖父→子的开局上下文。
6. **失败、重试、恢复和幂等语义是什么？**
   - 信封组装失败（父 turn 摘要取不到）→ 退化为裸 task + 显式标注 `envelope=degraded`，不许静默当"全上下文"用；
   - 成员回灌失败 → 父保留已得最佳结果（现有 `invoke_members_sequential` 语义保留）；
   - **不可逆操作上报失败**：先查实际效果（journal/event 或幂等查询）再决定重试或补偿，**不许**按"失败=没发生"盲重。
7. **如何验证？** §6 的 5 条验收用例，含一次真实多成员委派 run 的 journal 断言。

---

## 1. 诊断：委派是"一句话"，不是"一次交接"

```python
# lca/agent/member_invoke.py — 现状
observation = await send_and_wait(self._transport, role, task, timeout_s=self._timeout_s)
#                                                        ^^^^
# task 是调用者手写的字符串；成员的"世界" = 这一个字符串 + 可选的 workspace handoff block
```

ADR-0255 §4.6 的三条机制，LCA 现状逐条对照：

| 0255 §4.6 | LCA 现状 | 差距 |
|---|---|---|
| 子 agent 继承完整父 transcript（含 standing 注入） | 只收 task 文本 | **大**：成员不知道 SOUL/USER/记忆，开局身份真空 |
| 子产出回灌父 turn，父做同等尽调，不轻信完成报告 | `Result.from_observation` 直接转正 | **中**：observation 即被当事实用，无"证据核验"环节 |
| 不可逆操作上报失败：先查实际效果是否已发生，再定重试 | 失败即停/返回最佳结果 | **中**：停是对的，但没有"先验效果"的显式步骤 |

## 2. 取舍：不照搬全量 transcript

Muse 的子 agent 继承**完整**父 transcript——那是云端 VM、token 预算充足的形态。LCA 的成员常是同机轻量 agent 或 peer transport，全量 transcript 的 token 成本与隐私面（peer 可能是另一个用户的助理）都不划算。

本 ADR 的取舍：**信封 = standing 全量 + 父 turn 摘要 + 任务相关记忆投影**，而不是全量 transcript。

- standing 全量必须给：SOUL/IDENTITY/USER + 与任务相关的记忆条目——这是"我是谁/用户是谁"，没有它成员必然漂移；
- 父 turn 摘要（最近 N turn 的事实级压缩，不是原文）给"进行到哪了"；
- 对话原文、工具调用明细默认不给；成员需要时走 handoff bus 反向索取（ADR-0250 已有通道）。

## 3. 委派信封 `DelegationEnvelope`

```python
@dataclass(frozen=True)
class DelegationEnvelope:
    task: str                      # 本次委派的任务（现有）
    standing: StandingProjection    # SOUL/IDENTITY/USER 全文 + 任务相关记忆条目（ADR-0254 的 MEMORY.md 投影复用）
    parent_digest: str              # 父 turn 事实级摘要：已确认的事实、进行中的假设、明确排除的方向
    evidence_required: bool = True  # §4：回灌必须带 evidence 指针
    envelope_version: str = "1"
```

组装位置：`invoke_members_sequential`（pipeline 接力处，已有 handoff 拼接点，天然位置）；`TransportMemberInvoker.invoke` 保持裸 task 入口供底层直调，但 team/orchestration 层统一走信封。

退化规则：任一投影取不到 → 信封仍发出，但 `envelope_version="1-degraded"` 并在 `DelegationIssued` 事件里标注缺了哪块；**不许**把 degraded 信封当成全上下文用（下游做决策时可见）。

## 4. 回灌复核协议（父的尽调义务）

1. **只收 evidence，不收断言**：成员的 observation 若含结论性断言（如"已删除 X"），父必须看到支撑它的 evidence 指针（journal event id / 文件路径 / 工具返回原文），否则该断言不进父的事实集；
2. **独立核验**：关键断言父用自己的工具复核一次（读文件、查 journal），成本高于信任但低于重做——这是 0255 §4.6 "与自己动手同等的 due diligence" 的 LCA 版；
3. **不可逆失败三步**：① 查实际效果（journal 有无对应事件 / 幂等查询目标状态）→ ② 已发生：记为完成并补偿善后，不重试 → ③ 未发生：按现有重试/死信策略走（ADR-0093）。

## 5. 与现有机制的缝合点

- ADR-0037 journal as truth：`DelegationIssued` 事件 payload 扩展 `envelope_version` + `degraded_parts` 字段，回灌的 evidence 指针即 journal event id——复核链天然可审计；
- ADR-0254 continuous memory：`standing` 投影复用其 MEMORY.md 投影机制，不另起一套；
- ADR-0093 持续执行控制面：§4.3 的重试/死信走现有 WorkQueue，不新开；
- ADR-0187 assistant-agent：AssistantHome 即天然的 standing 来源（人设+记忆同目录），assistant 作为成员时信封组装零成本。

## 6. 验收标准（可直接抄的测试用例）

1. **信封非空断言**：任一经 team/orchestration 层发起的委派，`DelegationIssued` 事件 payload 含 `standing` 非空、 `parent_digest` 非空；裸 `TransportMemberInvoker.invoke` 直调不强制（底层通道）。
2. **退化标注断言**：人为让 `parent_digest` 取数失败，委派仍发出且事件里 `envelope_version="1-degraded"`、`degraded_parts=["parent_digest"]`。
3. **断言拒收断言**：成员 observation 为纯断言（无 evidence 指针），父的事实集不收录该断言，并记一条复核事件。
4. **不可逆失败三步断言**：mock 一个"上报失败但实际已发生"的成员调用，父走完查效果→记完成→不重试三步，journal 可查。
5. **真实 run 断言**：一次多成员 pipeline 委派 run，journal 里 `DelegationIssued → (成员 steps) → DelegationCompleted → 复核事件` 链条完整。

## 7. 决策记录（2026-10-01，李超授权 Athena 决定）

1. **peer 场景信封脱敏——采用 `standing_redacted` 变体**：跨信任边界（peer、走 transport）默认发脱敏信封，剥离 PII（姓名、住址、联系方式、账号标识等），保留任务相关上下文；同机 subagent 本来就继承 transcript，继续用全量。理由：最小权限 / need-to-know，与生产 agent 的 discretion 原则一致（knowing much, showing little）。
2. **父 turn 摘要生成器——journal step-tree 派生**：journal 是事实源，摘要从结构化记录派生，确定性、可审计、可复现、零额外模型成本；模型即时摘要有幻觉风险且不可复现，仅作 journal 缺失时的 fallback。
3. **`invoke(member, task)` 签名——直接升级为信封**：不新增 `invoke_with_envelope`（避免 API 双轨）；保留 `task: str` 作为便捷参数，内部统一构造最小信封，向后兼容。
