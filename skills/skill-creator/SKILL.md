---
name: skill-creator
description: "创建/改进当前助理自己的操作技能（skill）：访谈需求 → 按官方 skill-creator 规范撰写 SKILL.md（可含 resources/ 脚本与参考资料）→ 调用 create_assistant_skill 安装进本助理 Home 的 skills/ 目录 → activate_skill 加载，使新技能进入本助理的可用技能列表。触发：创建技能 / 新建 skill / 给我做一个技能 / 写一个技能 / 优化技能 / 改进现有技能 / 把刚才的操作做成技能 / 制作一个 SKILL.md。"
version: 1.0.0
references:
  - resources/skill-writing-guide.md
---

# skill-creator

把「我想创建一个技能」变成一次可交付的创作流程。创建的技能属于**当前助理自己**：安装到 `{assistant_home}/skills/<skill_id>/`，manifest 配置同步更新，之后本助理的 `<available_skills>` 会发现它，可直接 `activate_skill` 使用。

方法论改编自 Anthropic 官方 `skill-creator`（https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator/skills/skill-creator），保留其核心：捕获意图 → 访谈 → 撰写 SKILL.md（触发型 description + 渐进披露结构）→ 安装 → 测试/迭代。

## 前置检查

- 工具列表里**必须有** `create_assistant_skill`。没有 ⇒ 当前 run 未绑定助理（或部署未启用 assistant-runtime），直接告知用户无法创建技能。
- 已有技能用 `list_assistant_skills` 查看，避免 skill_id 冲突。

## 流程

### STEP 1 · 捕获意图

确认四个问题（能从对话历史推断的不必重问，只确认）：

1. 这个技能要让助理能做什么？
2. 什么时候触发？（用户说什么话 / 出现什么上下文时应该用到它）
3. 期望的输出格式是什么？
4. 是否需要测试用例？输出可客观验证（文件转换 / 数据抽取 / 代码生成 / 固定工作流）的技能建议做 2-3 个测试提示词；纯风格类技能可不做。

### STEP 2 · 访谈

追问边界情况、输入 / 输出格式、示例文件、成功标准、依赖。用 `askUserQuestion` 让用户选择关键决策（例如是否需要脚本、触发范围）。不要跳过：先想清楚再写。

### STEP 3 · 撰写 SKILL.md

先用 `read_skill_reference_once` 读取 `resources/skill-writing-guide.md`，再动笔。要点：

- frontmatter 必须有 `name` 和 `description`。`name` 即 skill_id（小写、连字符）。`description` 是触发主机制：写清「做什么」+「什么时候用」，宁可 pushy 一点。
- 正文 < 500 行；需要更多时用 `references/` / `scripts/` 渐进披露。
- 用祈使句、给示例、说明「为什么」而不是堆砌 MUST。

若技能需要脚本 / 参考文件（`resources/`、`scripts/`、`references/`、`assets/`）：

1. 在沙箱 / 工作区建一个**专用目录**，例如 `/mnt/data/skill-drafts/<skill_id>/`。
2. 用 `writeFile` 把 `SKILL.md` 和 `resources/...` 等文件写进该目录。
3. 安装时传 `sandbox_path` 指向该目录（见 STEP 4），附属文件会一并安装。

### STEP 4 · 安装进本助理 Home

调用 `create_assistant_skill`，二选一：

- 只有 SKILL.md：传 `skill_md`（含 frontmatter 的全文）。
- 有资源文件：传 `sandbox_path` = 上一步的**目录**（含 SKILL.md 与 resources/）。
- `skill_id` 可选，但若传了必须与 frontmatter `name` 一致。

安装会写入 `{assistant_home}/skills/<skill_id>/` 并更新 manifest（revision_seq++），只属于本助理，不影响全局 `~/.lca/skills/`。

失败处理：工具返回错误 ⇒ 原文告知用户。若是 frontmatter 缺 `name` / `description` 或资源路径非法，按错误消息修正后重试，同一参数最多重试 1 次。

### STEP 5 · 激活与验证

1. 调用 `activate_skill`（skill_id）把新技能的操作指南加载进上下文。
2. 按新技能自己跑一遍用户的核心诉求（或让用户给一个样本输入），检查输出是否符合预期。
3. 不满意则回到 STEP 3 修改 SKILL.md，重新调用 `create_assistant_skill` 覆盖安装（同 skill_id 会覆盖），再激活验证。

### STEP 6 · 汇报

向用户汇报（必须包含，不得编造）：

- `skill_id` 与安装路径（来自工具 Observation payload）
- 技能触发方式（description 的 when-to-use）
- 它已进入本助理的可用技能列表，下次相关请求会自动使用
- 若要删除：`delete_assistant_skill`（敏感，需用户确认）

## 禁止

- 不要用 `writeFile` / `runCommand` 直接往 `~/.lca/skills/` 或全局技能库写文件。安装只走 `create_assistant_skill`。
- 不要用 `import_skill` 代替（那是装 Market / URL 的全局技能，与角色身份无关）。
- 不要编造 `skill_id` / 安装路径 / frontmatter 校验结果。
- 不要跳过 STEP 1 / 2 直接写 SKILL.md。
- 不要创建没有 `name` + `description` frontmatter 的 SKILL.md（安装校验会拒绝）。
- 不要声称技能对其它助理可见（它是当前助理 Home 私有的）。