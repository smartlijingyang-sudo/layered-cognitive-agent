---
name: create-assistant
description: "创建新的个人助理（助手）：从 268 个角色档案中选一个，调用 create_assistant 工具在后端初始化助理并注册前端入口。触发：用户说创建助理/新建助手/帮我建一个助理/我想要一个XX助理。"
version: 2.0.0
references:
  - resources/department-catalog.json
  - resources/list_roles.py
---

# create-assistant

把「我想创建一个助理」变成一次设置完成的创建流程。从 268 个专家角色档案中选一个，助理自动获得该角色的完整人格和能力定义。

原则：**选项优先、输入最少** —— 能让用户点选的绝不要求打字。

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
| 设计 (design) | 9 | UI/UX 设计师、品牌guardian |
| 安全 (security) | 10 | AppSec、云安全、渗透测试 |
| 产品 (product) | 5 | 产品经理、需求分析 |
| 金融财务 (finance) | 9 | 财务分析师、税务策略 |
| 项目管理 (project-management) | 7 | PM、Scrum Master |

## 流程

### 1. 判断是否可以直接创建

用户一句话已说清「名字 + 角色」（例：「创建一个叫小架的后端架构师助理」或「用 engineering/engineering-backend-architect 创建一个助理」）⇒ 跳过提问，直接到第 4 步。

### 2. 选择部门（`askUserQuestion`）

读取 `resources/department-catalog.json`（用 `read_skill_reference_once`），按数量排序展示前 4 个部门 + 「更多部门」选项。

示例问题：「你的助理属于哪个领域？」
- 工程技术（42 个角色）
- 市场营销（42 个角色）
- 综合专业（58 个角色）
- 设计（9 个角色）
- 其他（让用户输入部门名或描述需求）

### 3. 选择角色（`askUserQuestion`）

用 `run_skill_script` 执行 `list_roles.py <department>` 获取该部门下的角色列表。展示前 3-4 个热门角色 + 「查看更多」。

示例问题（工程部门）：「选一个专家角色？」
- 后端架构师 ⚙️ — 系统设计、数据库架构、云基础设施
- 前端开发工程师 🎨 — React/Vue、性能优化、无障碍
- SRE 工程师 🔧 — 监控、故障恢复、容量规划
- 查看更多（列出该部门所有角色）

用户选「查看更多」⇒ 再次用 `askUserQuestion` 展示更多角色（分批，每批最多 4 个）。

### 4. 确认名字

如果用户没给名字，用 `askUserQuestion` 问：「助理叫什么？」给 2-3 个建议名（基于角色）+ 自定义。

### 5. 创建

调用 `create_assistant`：

```json
{
  "name": "<确认后的名字>",
  "description": "<角色描述 + 用户补充的职责>",
  "from_role": "<role_id，如 engineering/engineering-backend-architect>",
  "seed_user_md": "<可选：用户画像>"
}
```

失败处理：工具返回错误 ⇒ 原文告知用户；同一参数最多重试 1 次。

### 6. 汇报（必须包含全部要素）

成功后回复用户：

- 助理名字 + emoji
- 角色与能力（从角色档案描述）
- `assistant_id`（`asst_` 开头）
- 前端入口：`frontend_url` 非空 ⇒ 给出 `/agent/<agent_id>` 链接
- 提示：助理已获得该角色的完整人格，首次对话可以补充更多个人偏好

## 搜索模式

如果用户描述了需求但不知道选哪个角色（例：「我需要一个能帮我做数据分析的助理」），用 `run_skill_script` 执行 `list_roles.py --search 数据分析` 搜索匹配的角色，展示结果让用户选择。

## 禁止

- 不要用 `run_command` / 脚本在磁盘上手写助理目录。创建只走 `create_assistant` 工具。
- 不要编造 `assistant_id` 或前端链接。
- 不要在用户没确认名字前创建。
- 不要只展示 6 个旧模板。用户应看到完整的 268 个角色档案。
