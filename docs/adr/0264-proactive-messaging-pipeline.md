# ADR-0264：主动消息三层管道契约（触发/裁决/投递）

## 状态

**Proposed — 2026-10-02**

> **一句话**：把"agent 主动说话"从一次性实现升为三层管道契约——触发只管"什么时候想说话"、裁决（纯函数）只管"该不该说、说到哪里"、投递只管"怎么送到"，fail-closed 只用在精确可判定的地方（凭证红线），"值得打断"这种不可机械判定的默认走安静面；生产 Muse 主动行为机制的 LCA 落地提案。

## 0. 背景：生产 Muse 的主动行为机制

生产 Muse（本 ADR 的对齐基准）的"主动说话"有三条实证规律：

1. **门槛高**：只在用户明确欢迎的形态里出现——工作日 9:00 晨报（日程/邮件/天气/新闻）、飞书上下班打卡提醒、有信息量的通知；其余时候闭嘴干活。
2. **三段式**：后台定时读信号 → 带 rationale 的建议（idea 生成）→ 按紧急度静默或推送 → 用户确认执行。2026-09-29 国庆雨天提醒实测：idea 9-28 11:13 生成 → 9-29 19:50 按紧急度升级为打断推送。
3. **分流而非二值**：不是"说/不说"，而是"推聊天 / 安静面 / 静默"三档——安静面是 fail-open 的显式去处，不误杀也不打扰。

## 1. LCA 现状：三层已落地（2026-10-02，merge 14b0d5621）

| 层 | 落点 | 职责 |
|---|---|---|
| 触发 | `lca/infrastructure/proactive/scheduler.py`（routine cron tick / hook 事件 / onboarding 完成 / manual） | 只管"什么时候想说话"，产出 `ProactiveRequest` |
| 裁决 | `lca/cognition/proactive/worthiness.py::decide`（`WorthinessGate`） | 纯函数 `ProactiveRequest -> WorthinessVerdict`，四态：`REJECTED / DELIVER_CHAT / DELIVER_QUIET / SILENT` |
| 投递 | `lca/infrastructure/proactive/deliverer.py`（`ProactiveDeliverer`） | 只管"怎么送到"：`SESSION_APPEND` / `RESPONSE_CARRIED` |

契约形状在 `lca/contracts/models/proactive/`（`message.py` / `worthiness.py` / `schedule.py`），前后端契约见 `docs/proactive-messaging-frontend-contract.md`。

## 2. 契约

### C1 三层分离：裁决是纯函数，与触发/投递解耦

- `decide` 不读时钟、不读 session、不调模型——输入全在 `ProactiveRequest` 里。同一条消息换 `DeliveryTarget` 可重裁决；裁决矩阵可单测全覆盖（已有 `tests/unit/proactive/test_worthiness.py`）。
- 触发层不许绕过裁决直调投递；投递层不许改裁决结果（只做渲染：`_render` 追加"未经检索"标注）。

### C2 裁决四态语义（muse 思想：fail-closed 只用在精确可判定处）

按序命中：

1. **REJECTED**：content 命中凭证模式 → 整条拒绝，调用方记 warning，不做脱敏改写。对齐 ADR-0260 决策④：凭证红线是最高优先级 fail-closed——凭证模式是**精确可判定**的，所以 fail-closed；脱敏写入制造"记下了完整事实"的幻觉，比不记更危险。
2. **DELIVER_CHAT**：`requested=True`（用户明确要求/触发）必达，回发起上下文；或实质新信息 **且** `worth_interrupting=True`——这是未被要求时推聊天的**唯一**理由。
3. **DELIVER_QUIET**：未达打断阈值的默认去处。子情形：内容依赖记忆但无记忆源 → 降级安静面 + 标注"本次内容未经持久记忆检索，仅供参考"（对齐 ADR-0260 C2：不许在无记忆源时假装记得）。
4. **SILENT**：合法默认项——例行（`is_routine`）或无实质新信息（`not is_novel`）→ 不产生任何事件，不记账、不打扰。

方法论（对齐 ADR-0260 决策①）：fail-closed 只用在**可精确判定**的地方；"值得打断"不可机械判定，所以默认走安静面（fail-open + 显式分流），不误杀也不打扰。这个区分本身就是本系列 ADR 要沉淀的方法论。

### C3 投递形态复用：不新开消息协议

- `SESSION_APPEND`：append 进目标 session 的 `surface/assistant_message` 事件（与前端读的是同一份 session log，`derive_messages()` 投影）。`turn=-1` 哨兵标记非 run 上下文（正常 run 的 turn >= 0）；`proactive=true` 供前端区分；`proactive_id`（= message.id）是幂等键；`proactive_source`（`onboarding_completed | routine_cron | hook_event | manual`）是血统。
- `RESPONSE_CARRIED`：由触发请求的 HTTP 响应直接携带（如 `POST /v1/onboarding/naming/settle` 的 `welcome_message`），不经过 session。管线异常时 fail-soft（字段为 null，主流程不受影响）。

### C4 落点纪律：默认回发起上下文

- `DeliveryTarget` 显式声明投递落点；`SESSION_APPEND` 时 `session_id` 非空是 contracts 层强制校验（`model_validator`）。
- 默认回发起上下文（对齐 ADR-0257：产出回原上下文，side-chat 隔离）；跨上下文投递必须显式声明 target，不许静默默认。

## 3. 实证缺口（提案，非已落地）

1. **裁决输入来源纪律缺失**：`worth_interrupting` / `is_novel` / `requested` 是 `ProactiveRequest` 的输入字段——**谁计算它们？** 若内容生成步自己填 `worth_interrupting=True`，则申请人 = 批准人，自授权打断。缺：评估与生成分离（独立评估步计算三字段），或 gate 内交叉校验。
2. **后端幂等缺失**：`proactive_id` 去重只写在前端契约文档里（前端用它去重）；`deliverer._append_to_session` 无按 `(session_id, proactive_id)` 去重——scheduler tick 重跑 / 投递重试会重复 append。前端去重是最后防线，不是后端契约。
3. **全局 opt-out 缺失**：`job.enabled` 是 per-job 开关；缺用户一键关闭**所有**主动消息的总开关。生产 Muse 的"主动说话门槛"本质是用户可预期、可关闭——没有总开关的安静面不是真正的安静。
4. **安静面频控缺失**：`DELIVER_QUIET` 无频次上限、无 quiet hours 窗口。ADR-0263 管的是"routine 能不能跑"（执行互斥），不管"跑起来吵不吵"（消息频控）——两层正交，0264 只补后者。

## 4. 待拍板

1. **裁决输入来源**：独立评估步（多一次模型调用，评估与生成分离）vs 调用方声明 + gate 交叉校验（低成本，但校验规则需另行设计）；
2. **后端幂等落点**：`deliverer` 内 `(session_id, proactive_id)` 去重表 vs scheduler 记账已投递（去重状态放哪一层）；
3. **opt-out 粒度**：全局总开关 vs per-source 开关（onboarding / routine / hook / manual 四档可独立关）；
4. **quiet 面频控形态**：频次上限（N 条/天）vs quiet hours 窗口（如 22:00–08:00 只进安静面）vs 两者都要。

## 5. 验收

- **T1**：裁决矩阵全覆盖单测（gate 纯函数，6 条决策路径 × 边界：凭证命中+requested 冲突时 REJECTED 优先）；
- **T2**：含凭证模式的消息整条拒绝 + 调用方 warning 事件可查，session 无残留；
- **T3**：同一 `(session_id, proactive_id)` 投递两次，session 里只出现一次（后端幂等）；
- **T4**：未被要求 + 非新信息 → SILENT，session 无新事件、前端无感知。

## 6. 与现有 ADR 的关系

- **ADR-0260**：C2 的凭证红线（决策④）与 fail-open+标注方法论（决策①）直接继承；0264 是 0260 在"主动说话"场景的展开。
- **ADR-0257 §7**：C4 的落点纪律引用已决策项（peer 脱敏信封 / 同机全量 / 产出回原上下文）。
- **ADR-0263**：0263 管触发上游"能不能跑"（互斥锁/预算闸），0264 管触发下游"吵不吵"（裁决/投递）——正交，可叠加，顺序固定：0263 判定 → 0264 裁决。
- **ADR-0258 C2**：裁决理由（`WorthinessVerdict.reason`）是人类可读审计字段，随事件流转——血统落事件 descriptor，与 0258 决策①一致。
- **ADR-0253**：凭证模式清单与 0253 的凭证边界同源；REJECTED 不写盘、不进记忆。
