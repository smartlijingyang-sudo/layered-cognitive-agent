# First-party operational skills（内容包）

与 `roles/` 同级：回答「**怎么做**」的操作知识，不进 `lca` Python 包。

| 路径 | 作用 |
|------|------|
| `skills/<skill_id>/SKILL.md` | 技能正文（YAML frontmatter + markdown） |
| `skills/<skill_id>/resources/` | 可选附属文件（挂载进沙箱） |

启动时 `resolve_skill_store()` → `ensure_bundled_skills()` 幂等安装到
`~/.lca/skills/`（`content_hash` 变化才重写）。

当前包：

| skill_id | 说明 |
|----------|------|
| `officecli` | Office 平面知识层（ADR-0054）；binary 在 terminal 镜像 |

**不要**把 Market 下载的 skill 提交到本目录；Market 仍走 `import_skill`。
