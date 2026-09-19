---
name: create-assistant
description: "创建新的个人助理（助手）：五状态向导（部门→角色→SOUL 对齐→取名→创建），从 268 个角色档案中选一个或自定义角色，对齐 SOUL 后调用 create_assistant 工具初始化助理并注册前端入口。触发：用户说创建助理/新建助手/帮我建一个助理/我想要一个XX助理。"
version: 3.0.0
references:
  - resources/department-catalog.json
  - resources/list_roles.py
---

# create-assistant

把「我想创建一个助理」变成一次设置完成的创建向导。流程是**五状态状态机**，每一步都有明确的出口条件：

```
DEPARTMENT → ROLE → SOUL_ALIGN → NAME → CREATE
```

原则：**选项优先、输入最少** —— 能让用户点选的绝不要求打字。但 **SOUL 对齐不可跳过**：未通过完整度校验不允许创建。

## 前置检查

- 工具列表里**必须有** `create_assistant`。没有 ⇒ 当前部署未启用助理能力（需 `web-assistant` profile），直接告知用户。

## 角色档案库

268 个专家角色，分 19 个部门。用 `read_skill_reference_once` 读取 `resources/department-catalog.json` 获取完整目录。用 `run_skill_script` 执行 `list_roles.py` 按部门查看或搜索。

主要部门速查：

| 部门 | 数量 | 代表角色 |
|---|---|---|
| 工程技术 (engineering) | 42 | 后端架构师、前端开发、SRE、DevOps |
| 市场营销 (marketing) | 42 | SEO 专家、内容策略、社交媒体运营 |
| 综合专业 (specialized) | 58 | 商业策略师、数据隐私官、CFO |
| 游戏开发 (game-development) | 20 | Unity/Unreal/Godot 工程师 |
| 设计 (design) | 9 | UI/UX 设计师、品牌 guardian |
| 安全 (security) | 10 | AppSec、云安全、渗透测试 |
| 产品 (product) | 5 | 产品经理、需求分析 |
| 金融财务 (finance) | 9 | 财务分析师、税务策略 |
| 项目管理 (project-management) | 7 | PM、Scrum Master |

## 五状态向导

### STATE 1 · DEPARTMENT（选部门）

读取 `resources/department-catalog.json`（用 `read_skill_reference_once`），按数量排序展示前 4 个部门 + 「更多部门」选项。

示例问题：「你的助理属于哪个领域？」
- 工程技术（42 个角色）
- 市场营销（42 个角色）
- 综合专业（58 个角色）
- 设计（9 个角色）
- 其他（让用户输入部门名或描述需求）

**出口条件**：选中一个部门。用户直接说领域描述时，映射到最近的部门。

### STATE 2 · ROLE（选角色或自定义）

用 `run_skill_script` 执行 `list_roles.py <department>` 获取该部门下的角色列表。展示前 3-4 个热门角色 + 「查看更多」+ 「自定义角色」。

示例问题（工程部门）：「选一个专家角色？」
- 后端架构师 ⚙️ — 系统设计、数据库架构、云基础设施
- 前端开发工程师 🎨 — React/Vue、性能优化、无障碍
- SRE 工程师 🔧 — 监控、故障恢复、容量规划
- 查看更多（列出该部门所有角色）
- 自定义角色（不用角色卡，按用户描述生成专属 SOUL）

**出口条件**：选中一个角色卡，或选择「自定义角色」。STATE 5 时角色卡路径传 `from_role`，自定义角色路径传 `custom_role=true`，两者必须二选一。

搜索模式：用户描述了需求但不知道选哪个角色（例：「我需要一个能帮我做数据分析的助理」），用 `run_skill_script` 执行 `list_roles.py --search 数据分析` 搜索匹配的角色，展示结果让用户选择。

### STATE 3 · SOUL_ALIGN（SOUL 对齐，不可跳过）

这是向导的核心。目标是产出一份**通过完整度校验的最终 SOUL**。

#### 角色卡路径

把角色卡 backstory 作为 SOUL 草稿展示给用户，说明这份草稿已经具备角色的完整人格。如果用户确认，把草稿整理成包含四个核心语义段的 Markdown：

- `## 🧠 身份`
- `## 🎭 性格`
- `## 🛠 能力`
- `## 🗣 语气`

如果用户要调整（「语气更活泼」「补充 XX 能力」），按用户描述修改草稿，再让用户确认。

#### 自定义角色路径

用户没有选择角色卡时，根据用户描述**生成完整 SOUL 草稿**，必须包含四个核心语义段（身份 / 性格 / 能力 / 语气）。逐段展示给用户确认或修改。

#### 完整度校验（fail-closed）

最终 SOUL 必须满足：

1. 去除空白后长度 >= 200 字符（中文）。
2. 包含全部四个核心语义段标记：`## 🧠 身份` / `## 🎭 性格` / `## 🛠 能力` / `## 🗣 语气`。

安全边界 / 记忆规则 / 错误处理 / 红线四段由模板预置默认内容，**不需要**用户手写。

**出口条件**：用户确认最终 SOUL。如果 `create_assistant` 返回 SOUL 校验失败（错误消息会指出缺哪一段），回到本状态继续补充，**绝不允许降级用模板 SOUL 创建**。

### STATE 4 · NAME（确认名字）

如果用户没给名字，用 `askUserQuestion` 问：「助理叫什么？」给 2-3 个建议名（基于角色标题）+ 自定义。

**出口条件**：用户确认名字。

### STATE 5 · CREATE（创建）

调用 `create_assistant`。**根据 STATE 2 的选择二选一传参**：

角色卡路径（用户选了角色卡）：

```json
{
  "name": "<确认后的名字>",
  "description": "<角色描述 + 用户补充的职责>",
  "from_role": "<role_id，如 engineering/engineering-backend-architect>",
  "soul": "<STATE 3 对齐后的最终 SOUL 全文>",
  "inherit_from": "<当前 assistant_id（在本助理对话内创建时默认带上）>",
  "seed_user_md": "<可选：用户画像（称呼/服务对象/偏好）>"
}
```

自定义角色路径（用户选了「自定义角色」）：

```json
{
  "name": "<确认后的名字>",
  "description": "<用户描述 + 补充的职责>",
  "custom_role": true,
  "soul": "<STATE 3 生成的完整 SOUL 全文>",
  "inherit_from": "<当前 assistant_id（在本助理对话内创建时默认带上）>",
  "seed_user_md": "<可选：用户画像（称呼/服务对象/偏好）>"
}
```

- `soul` 传 STATE 3 对齐后的最终 SOUL。非空时它覆盖 `from_role` backstory；安全边界/记忆规则/错误处理/红线由模板自动补全。
- `from_role` 与 `custom_role` 必须二选一：带 `soul` 创建时两者都缺会被工具拒绝，回到 STATE 2。
- `inherit_from` 默认取当前对话所在 assistant 的 `assistant_id`（复制其技能与工具/授权策略为快照）。用户明确不要继承时省略。
- `seed_user_md` 在 SOUL_ALIGN 顺带问到的用户画像（称呼 / 服务对象 / 偏好）非空时传入。

失败处理：工具返回错误 ⇒ 原文告知用户。若是 SOUL 校验失败，按错误消息指出的缺段回到 STATE 3 继续对齐；同一参数最多重试 1 次。

## 汇报（必须包含全部要素）

创建成功后，回复用户并**强制复述**以下字段（来自工具 Observation payload，不得编造）：

- `assistant_id`（`asst_` 开头）
- 助理名字 + emoji
- `personality`（从 SOUL 提取的性格要点）
- `tone`（语气要点）
- `capabilities`（能力清单：目标 / 工具 / 技能）
- 前端入口：`frontend_url` 非空 ⇒ 给出 `/agent/<agent_id>` 链接

示例汇报：「已创建助理 **小架 🏛️**（`asst_...`）。性格：结论先行、直接坦诚；语气：专业务实。能力：系统设计、数据库架构、云基础设施。入口：/agent/agt_...」

## 禁止

- 不要用 `run_command` / 脚本在磁盘上手写助理目录。创建只走 `create_assistant` 工具。
- 不要编造 `assistant_id` 或前端链接。
- 不要在用户没确认名字前创建。
- 不要跳过 SOUL_ALIGN 直接创建。
- 不要用降级模板 SOUL 代替用户确认的 SOUL 创建（SOUL 校验失败必须继续对齐）。
- 不要只展示 6 个旧模板。用户应看到完整的 268 个角色档案。
