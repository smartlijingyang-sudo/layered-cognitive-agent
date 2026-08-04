# ADR-0036: 废除金融隐喻——团队认知词汇统一为「回报记录 / 咨询义务」

## 状态
Accepted

## 背景
代码库中长期存在一套会计金融隐喻：`TeamAwareness.results` 被称为「委派账本
（delegation ledger）」，其写入被称为「记账 / 入账」，`Settlement` 组件被称为
「结算义务」，状态机终态判断被称为「结算（settled）」，组合根校验被称为「对账」。

词源考证：`ledger` 一词来自已删除的旧类 `DelegationLedger`（ADR-0015 时代的
`lca/contracts/team_progress.py`）。ADR-0035 把该类溶解为 `TeamAwareness.results`
+ `MemberStatus` 后，**类死了，隐喻却泄漏进了 docstring、注释、测试名与文档**，
成为化石词。

问题：

1. **领域错位**：本框架是认知 agent 团队协作框架，不是金融系统。「账本 / 结算」
   让新读者误以为存在会计式双份记账或对账语义，而实际机制是「成员返回 → 记录 →
   投影」（提示词渲染 + 幂等查询）。
2. **一词两指**：测试中 `ledger` 既被用来指 `TeamAwareness.results`（回报记录），
   又被用来指 `MemberStatus`（状态板），同一隐喻覆盖两个不同概念。
3. **死名复活风险**：化石词散落在 20+ 处，任何一处被新代码引用都会让死隐喻复活。

## 决定

以团队领域原生词汇统一替换金融隐喻。核心概念不变——**append-only 记录 +
纯函数投影**（提示词渲染与幂等查询是该记录的两个无状态投影）——只换词汇：

| 旧（金融隐喻） | 新（团队领域词汇） | 所指 |
| --- | --- | --- |
| 委派账本 / delegation ledger | **委派回报记录** | `TeamAwareness.results` |
| `Settlement` / 结算义务 | **`ConsultDuty`** / 咨询义务 | `TeamAwareness.consult_duty` |
| `settle_delegation` | **`record_delegation_return`** | 成员返回落定后登记（状态板或回报记录） |
| `settlement_board` | **`duty_board`** | 读取咨询义务状态板 |
| `all_settled` | **`all_terminal`** | 与既有 `is_terminal_status` 同源 |
| `_record_in_ledger` | **`_record_report`** | 回报记录追加 |
| `_LEDGER_EXCLUDED_KINDS` | **`_REPORT_EXCLUDED_KINDS`** | 提示词 CONTEXT 去重排除集 |
| 记账 / 入账 | 记录 / 登记 | 写入动作 |
| 结算进度 | 应答进度 | 状态板语义 |
| 对账 | 核对 | 组合根校验 |

选词依据：

- **回报（report）** 是既有活词汇——提示词变量 `member_reports_text`、语义键
  `MEMBER_REPORTS`、文案「成员回报」早已使用，本次只是让代码与文档向它看齐。
- **ConsultDuty** 与活词汇 `LeadMandate.CONSULT` / `MustConsultAllMembers`
  （"must consult all" 不变量）同根；不复用化石词 `ConsultationState` 的词形。
- **terminal** 与既有 `role_status_rules.is_terminal_status` /
  `_TERMINAL_STATUSES` 同源，终态分类逻辑仍只有一份。

配套清理：

- `scripts/check_no_any.py` 删除失效白名单 `ledger_factory.*Any` 与
  `_team_progress:\s*Any`（对应符号均已不存在）。
- `docs/glossary.md` 化石表新增一行记录本措辞废除；`DelegationLedger /
  team_progress` 墓碑行保留（死名 → 活名映射正是化石表的职责）。
- ADR-0015 / ADR-0034 / ADR-0035 是历史快照，正文**不重写**（本目录维护规则）；
  其中的旧名由本 ADR 映射表与 glossary 化石表承担翻译。
- `tests/test_routing_prompt_ledger.py` 改名为
  `tests/test_routing_prompt_reports.py`。

## 后果
- 正面：`ledger / 账本 / settlement / 结算` 在代码、测试、脚本、活文档中归零；
  词汇与提示词侧（MEMBER_REPORTS / 成员回报）自洽；终态词汇收敛到 terminal 单源。
- 负面：breaking change（`Settlement` / `settlement` 字段、`settle_delegation`、
  `settlement_board`、`all_settled` 更名），无 shim（沿用 ADR-0030 约定）。
- 中性：`Settlement` 的字段结构（member_status / max_attempts / attempts）与全部
  行为语义不变；`DelegationResult` / `results` 等本就中性的契约名不受影响。

## 相关
- Keeps：TeamAwareness 统一会话（ADR-0035）、contracts 无行为类（ADR-0015）、
  领域语言 Lead / Coordination（ADR-0030）。
