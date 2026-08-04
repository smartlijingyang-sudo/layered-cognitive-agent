# ADR-0035: TeamAwareness —— 统一 lead 团队认知，废除会话分裂

## 状态
Accepted

Supersedes: ADR-0030 中「单 session 槽 = ConsultationState | RoutingState」的会话语义；
ADR-0034 中「LeadStrategy 按 mandate 选择会话类型」的组合分支。
（两者其余决定——领域语言、封闭策略——继续有效。）

## 背景
ADR-0030 钉死领域语言、ADR-0034 收敛团队形态单一事实来源后，lead 的「控制面会话」
仍以**两个并列 dataclass** 表达：`ConsultationState`（consult / board）与
`RoutingState`（routing），经联合别名 `ControlSession = ConsultationState | RoutingState`
挂在 `AgentState.session` / `RunContext.session` 单槽上。为了让消费方在运行期分辨
「当前是哪种会话」，派生出一整条类型窄化与分发链：

1. **窄化函数四件套**：`as_consultation` / `as_routing` / `require_consultation` /
   `require_routing`——每个消费方先 `isinstance` 判别会话种类再取字段。
2. **mandate→会话映射函数**：`mandate_uses_consultation_session(mandate)`，把「哪种
   授权用哪个 dataclass」这一实现细节升格为公共契约。
3. **Reasoner 按会话分支**：`SupervisorReasoner.generate_candidates` 内用
   `if as_consultation … elif as_routing …` 选模板与提示词变量；组合期还需
   `SupervisorReasoner.from_simple` 把 solo reasoner「升级」成 supervisor 版本。
4. **字段白名单断言**：`assert_consultation_field_whitelist` /
   `assert_routing_field_whitelist` 用测试看守两个 dataclass 的字段面，防止彼此语义
   互相渗透——裂缝本身成了需要看守的资产。

共同根因：**consult/board 与 routing 的本质差异只是「有无结算义务」一个比特，
却被建模成两个平行类型 + 联合 + 窄化 + 分发**。消费方不信任对象、反复在对象外部
询问「你是哪种会话」，而不是让对象自己提供所需。`generate_candidates`（n 恒为 1、
并无候选竞争）与 `Supervisor*` 前缀（ADR-0030 已废除 SupervisorMode 的残留词根）
进一步放大了认知负担。

## 决定

本质模型一句话：**lead 的团队认知是一个 `TeamAwareness`——名册 + 委派账本 +
可选结算义务；结算义务是它的可选组件，不是它的分裂依据。**

1. **`TeamAwareness`（contracts/team_awareness.py）**：单一具体类型，字段
   `teammates` / `results`（委派账本）/ `settlement: Settlement | None` /
   `assigned_roles` / `notes`。挂在 `AgentState.team_awareness` 与
   `RunContext.team_awareness` 单槽；solo / member 为 None。
2. **`Settlement`**：结算义务组件——`member_status`（必问成员状态板）+
   `max_attempts`（组合期注入，契约不私藏默认）+ `attempts`（重试计数）。
   `settlement is None` 即自由 routing，这是两种授权的唯一差异。
3. **废除类型窄化**：删除 `ControlSession` 别名与 `as_*` / `require_*` 四件套。
   消费方只读 `state.team_awareness`，再按 `settlement` 有无取分支——这是对**字段**
   的判空，不是对**类型**的窄化。
4. **废除 mandate→会话映射**：删除 `mandate_uses_consultation_session`。组合根
   （`defaults._lead_strategy`）按 `_SETTLING_MANDATES`（consult / board）决定
   `board` 是否注入，`LeadStrategy` 只接收 `board: MemberStatus | None`。
5. **Reasoner 坍缩为单一 `PromptReasoner`**：无 awareness 走 react 模板；有
   awareness 时并入 awareness 自渲染的变量（`build_awareness_variables`）与默认
   模板（`default_template_for`）。删除 `SupervisorReasoner` / `SimpleReasoner` /
   `from_simple`，组合根不再按 mandate 升级 reasoner。协议方法
   `generate_candidates` → `generate_thoughts`（如实表达「产出思考文本」）。
6. **行为落在实现层纯函数**：结算记账 `settle_delegation`、状态板读取
   `settlement_board`、账本幂等 `cached_delegation_observation` 均为 layer1 纯函数，
   依据 `settlement` 有无分流。contracts 仍只放数据（遵循 ADR-0015）。
7. **删除字段白名单断言**：概念统一后无裂缝可守；dataclass 纯净由
   ADR-0015 门禁兜底。

## 后果
- 正面：会话概念从「两个类型 + 联合 + 四窄化 + 一分发」收敛为「一个类型 + 一个可选
  组件」；消费方零 `isinstance`、零类型窄化；Reasoner 单一实现，组合根无 reasoner
  分支；`Supervisor*` / `*candidates` 残留词根清除。
- 负面：breaking change，无 shim（沿用 ADR-0030 约定）；`team_awareness` 槽改名
  波及全部既有 `session=` 调用点。
- 中性：自由 routing 的账本语义不变——`results` 只在无 settlement 时累积，
  settlement 路径的结算进度仍由状态板表达，避免双份事实源。

## 相关
- Supersedes（部分）：ADR-0030（单 session 槽的会话分裂语义）、ADR-0034（按 mandate
  选择会话类型的组合分支）。
- Keeps：五层分层（ADR-0001）、封闭 TeamStrategy / TeamSpec（ADR-0034）、
  contracts 无行为类（ADR-0015）、领域语言 Lead / Coordination（ADR-0030）。
