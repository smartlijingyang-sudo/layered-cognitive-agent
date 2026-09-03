# AGENTS.md — Rejected Agent Notes

考虑过但未通过的设计提案沉淀在此。遵循[根指令](../README.md)和[文档标准](../../AGENTS.md);`proposed/` → `rejected/` 的跃迁规则见 [`proposed/AGENTS.md`](../proposed/AGENTS.md)。

## 留一条 rejected note 的判定

`rejected/` **只保留"还能劝退未来人"的提案**。判定标准(三条满足任一即可留):

- **路径依赖清楚**:未来有人基于类似动机再次提案时,读完就能明白"这条路已经有人走过、堵在 X";否则删。
- **否决理由涉及多个 seam 或 ADR 边界**:简单换实现的否决不必留,git commit + PR 描述已足够。
- **配套证据(issue / 历史 ADR / profile 拓扑)仍可索引**:链接未失效,能反向追到否决现场。

不满足以上三条 → 直接删除**整组三元组**(`.md` + `.zh.md`(若存在) + `i18n.yaml`(若存在))。

## 与 proposed 段的差异(rejected 的保留面)

rejected note 是"提案冻结版":保留 `proposed/` 当时的所有章节(`## Problem` / `## Proposal` / `## Acceptance criteria`(可保留)/ `## Risks`(可保留)),**不再改动正文**。判决理由写在 `Status:` 行的尾部一行:

```markdown
Status: rejected — <one-line verdict>
```

verdict 必须能让读者在不读全文的情况下判断"这条路为什么不再被考虑"。禁止写成"暂时不做"、"后续再看"、"优先级低"这种留口子的措辞——这种条目该删。

## 何时该删一组 rejected 三元组

任一条件满足即删:

- **理由随时间失效**:底层机制、依赖、Profile 拓扑已经变了,旧否决不再能劝退当下提案。
- **指向的文件 / ADR / PR 已不存在**,且无替代链接。
- **新 note 完整覆盖了旧否决**(用 `### Why not <X>?` 子节在新 note 的 `## Alternatives considered` 中取代了它)。

删除动作不留骨架、不留 `DELETED.md` 占位文件——根 README §7 明确"archived append-only",`rejected/` 不享受这一保护,反过来说它**没有**"冻结不许动"的豁免。

## 删除前的"交叉修复"

删三元组的同时必须:

- `git grep` 搜原文件名(`YYYY-MM-DD-<topic>.md`),把**所有** inbound 链接要么改写成现存替代 note 的相对链接,要么删除该引用段落。
- 不能保留"指向不存在的 note"的死链——根 README 强调"跨 note 引用一律相对 markdown 链接",死链属于强制修复范畴。

## 当前状态

本目录为空。
