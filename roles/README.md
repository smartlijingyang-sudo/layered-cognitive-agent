# 角色库（自动组队内容包）

本目录是 `mode=auto` 自动组队的角色内容包，与引擎代码零耦合（ADR-0042）。
内容源自 [agency-agents-zh](https://github.com/jnMetaCode/agency-agents-zh)（与
agency-orchestrator 生产环境使用的专家库一致），共 200+ 张详细角色卡。

`gateway/role_library.py::FileRoleLibrary` 扫描本目录，把每个 `.md` 文件解析为一张
`RoleCard`；`LLMTeamCaster` 只看到精简索引，选中后才读取全文。

## 覆盖机制

设置环境变量 `AGENCY_ROLES_DIR` 指向其它目录即可整体替换本库：

```bash
export AGENCY_ROLES_DIR=/path/to/your/roles
```

## 角色卡格式

每个角色一个 `.md` 文件，`role_id` = 相对路径去掉扩展名（如 `product/product-manager`），
顶层目录名即部门。frontmatter 必须包含 `name`（展示名）与 `description`（一句话职责，
也是组队提示词里供 LLM 匹配的摘要）；frontmatter 之后的全部正文作为该角色的
`backstory` 注入 Agent：

```markdown
---
name: 产品经理
description: 负责需求分析、优先级排序与产品方案设计。
emoji: 🧩
---

# 产品经理

## 身份定义
...
```

## 约束

- 没有带 `name` 的 frontmatter 的 `.md`（如本文件）会被扫描跳过；
- 正文为完整专家提示词，会进入成员 Agent 的 system prompt；
- 自动选角时 LLM 必须使用完整 path（`category/role-name`），如 `design/design-ux-researcher`。
