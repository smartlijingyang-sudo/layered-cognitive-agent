# AGENTS.md — Implemented Agent Notes

落地后的决策沉淀在此。遵循[根指令](../README.md)和[文档标准](../../AGENTS.md);`proposed/` → `implemented/` 的跃迁规则见 [`proposed/AGENTS.md`](../proposed/AGENTS.md#升到-implemented)。

## 保持一条 implemented note 与现状一致

同一次改动里,凡是改动文件路径、符号名、默认值、机制归属,都要**就地**重写对应 note 的事实陈述;不追加"变更史"段落、不在文末补 issue 链接。

当一条 shipped note 不再能指导未来工作时,把它整组三元组迁到 [`archived/AGENTS.md`](../archived/AGENTS.md) 进入冻结态;**不要**靠"留着提醒大家"的动机继续维护它。

### 这不是"可以改写决策本身"的许可

只能更新事实落点。**翻转决策或推翻 rationale 必须新开一条 note 并交叉链接**;完全被取代的旧 note 是否允许合并删除,见[根 README](../README.md)的合并规则。

## 与 proposed 段的差异(implemented 的现在时)

`## Decision` 用现在时描述"现状是什么",不写"我们将...",不写"待办",不写"未来优化方向"。`## Acceptance criteria` / `## Risks` 在跃迁时折叠为 `## Consequences`,或保留为 `## Verification` / `## Testing`(同样描述现状,不写计划)。

跃迁 checklist(同一 PR 内):

- 文件从 `proposed/<class>/YYYY-MM-DD-<topic>.md` → `implemented/<class>/YYYY-MM-DD-<topic>.md`
- `Status: proposed` → `Status: implemented`
- `## Proposal`(将来时)→ `## Decision`(现在时)
- `## Acceptance criteria` / `## Risks` → `## Consequences` 或 `## Verification` / `## Testing`
- `## Alternatives considered` 保留,逐条仍可指认
- 若中译 `.zh.md` 已存在,同步移动并对齐章节标题

## 当前状态

本目录为空,等待第一条 note 由 `proposed/` 跃迁而来。
