# AGENTS.md — Archived Agent Notes

`archived/` 下的三元组是**冻结的历史记录**,不是当前行为规范。遵循[根指令](../README.md)和[文档标准](../../AGENTS.md);归档触发条件见 [`implemented/AGENTS.md`](../implemented/AGENTS.md)。

## 强约束(冻结即永冻)

归档完成的那一刻起,**任何**以下动作均视为破坏归档完整性:

- 编辑、移动、重排、删除、翻译、追加注释、修补格式、补 sidecar、改 frontmatter
- 把归档文件当作"现行权威"去引用其决策或默认值
- 重命名 / 改分类(`<class>/` 子目录)
- 修改 `Status:` 行 / `Archived:` 行 / 文件名中的日期段
- 把归档文件移回 `proposed/` / `implemented/` / `rejected/`(已归档即终态)

唯一允许的操作见下一节。

## 唯一允许的归档动作

`implemented/<class>/YYYY-MM-DD-<topic>.md` → `archived/<class>/YYYY-MM-DD-<topic>.md` 的跃迁,**严格限定**为下列五项:

1. **整体搬迁整组三元组**:`.md` + `.zh.md`(若存在) + `i18n.yaml`(若存在)一起移动到 `archived/<class>/`,**不拆、不丢、不补**。
2. 在 `.md` 与 `.zh.md` 中,**紧贴** `Status: implemented` 行下方插入一行 `Archived: YYYY-MM-DD`(两个文件同一行文本一致)。
3. 重新记录 `i18n.yaml` sidecar 中的 manifest hash(若存在);hash 算法与根 README §5 中"archived manifest 哈希 append-only"保持一致。
4. 修复或删除指向该归档 note 的 inbound 链接;**不**反向校验归档 note 的 outbound 链接是否还活着。
5. 把 append-only manifest(`archived/manifest.json` 或等价位置)追加新条目;不修改既有条目。

上述五条之外的任何字符级修改,即使是"修一个错别字"——**禁止**。归档文件不接受任何形式的"修正"。

## 与其他 lifecycle 的差异

- **不参与三态闭集**:`Status:` 行**保持** `Status: implemented` 不变;`Archived:` 行是路径级归档的标记,不是 `Status:` 的第四个取值。
- **可被 active prose 引用**:出于"故意引用历史"的目的,active(`proposed/` / `implemented/`)的 prose 可以**指向**归档 note;反过来不允许。
- **文档门禁跳过归档源**:根 README §5 列出的未来门禁在遍历 active 索引时跳过 `archived/` 子树,避免误把冻结内容当作约束源。

## 门禁契约(`scripts/verify_notes_archived.py`)

本批次**不实现**该脚本;根 README §5 已声明"等首条 archived 出现再启用"。`archived/AGENTS.md` 是该脚本的契约所有者,正式启用前所有动作以上述五条手工执行为准。脚本落地后必须检查:

- 归档子目录只出现在 close-set class 列表(`contract` / `primitive` / `seam` / `profile` / `runbook` / `postmortem`)
- 每个归档三元组完整(`.md` + 同步 `.zh.md` + `i18n.yaml`)
- `Archived:` 行紧贴 `Status: implemented`,两个文件同一文本
- manifest hash append-only(只能加,不能改 / 删既有条目)
- `Status:` 第四行不是 `archived`,且不是 `rejected` / `proposed`

## 当前状态

本目录为空。
