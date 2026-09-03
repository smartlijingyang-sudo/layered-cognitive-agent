# AGENTS.md — Proposed Agent Notes

草稿与未实施决策在此。遵循[根指令](../README.md)和[文档标准](../../AGENTS.md);门禁在步骤三落地前**不强制**,文件名、header 格式请人工对齐。

## 写一条新 note

1. 文件名:`YYYY-MM-DD-<topic>.md`,首次提出日期取自 git log 上最早的 commit 时间(可用 `git log --diff-filter=A --follow --format='%ai' -- docs/adr/<类似 ADR>` 估算;不确定就取提交当周的工作日)。
2. Header 三行,见[根 README#3.1](../README.md#31-header三行硬约束)。
3. Body 从 `## Problem` 开始;**不要写"我打算..."** —— Problem 段描述动机,不含解。
4. `## Proposal` 用将来时;`## Acceptance criteria` 写**可观察的状态**,不是 checklist。
5. `## Alternatives considered` 强制,见[根 README#3.3](../README.md#33-alternatives-considered强制)。
6. 跨 note 引用一律相对 markdown 链接(`[xxx](../../implemented/contract/...)`),不写裸编号。

## 升到 `implemented/`

实施开始后,**同一个 PR** 内:

- 文件从 `proposed/<class>/...md` 移到 `implemented/<class>/...md`
- `Status: proposed` → `Status: implemented`
- `## Proposal` 改写为现在时的 `## Decision`
- `## Acceptance criteria` / `## Risks` 折叠为 `## Consequences` 或保留为 `## Verification` / `## Testing`(描述现状,不写计划)
- 中文 `.zh.md` 和 `i18n.yaml` 同步移动;若实施后才补中译,本步就补
- 跑 `python scripts/check_notes_tree.py`(步骤三才接 verify-all,目前是手工 sanity check)

## 当前状态

本目录为空,等待步骤二产出第一条种子 note。
