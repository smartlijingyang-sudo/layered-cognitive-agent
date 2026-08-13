# ADR-0054: OfficeCLI Office 平面 — 沙箱二进制 + Bundled Skill + 路由

## 状态

Accepted

## 背景

Agent 需要稳定创建/编辑 Word / Excel / PowerPoint。现有路径依赖
`anthropics-skills-docx|pptx|xlsx` + `python-docx` / openpyxl / npm `docx`，
API 碎片化、布局难自检、模型易在运行时 `pip/npm install` 失败。

[OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) 提供单一二进制、路径 DOM、
`--json`、结构化错误与 `view issues` 自愈环，适合作为 **Office 文档执行平面**。

## 决定

### 一、三层分工（不新增专用 Tool）

| 层 | 职责 | 位置 |
|---|---|---|
| **Capability** | 沙箱预装固定版 `officecli` binary | `deploy/onlyboxes/Dockerfile.terminal` |
| **Knowledge** | 操作知识 SKILL.md（LCA 适配） | 仓库 `skills/officecli/` → seed 到 SkillPackageStore |
| **Routing** | 附件格式 → 优先 `officecli` | `format_routing.py` |
| **Execution** | 现有 `run_command` / `run_skill_script` | 无新 Tool 类 |
| **Harvest** | 即时产物 delta；Office 在 close/export/收口发一张 Work | 见 ADR-0046 一·附 |

禁止：

- 为每个 officecli verb 注册 LCA Tool；
- 运行时 `curl | bash` 安装 binary；
- 在 host 跑 officecli 绕过 run-bound sandbox；
- guest 内起 `officecli mcp` 作为主路径。

### 二、Bundled skill seed（ADR-0048 扩展）

- 第一方 skill 内容包放在仓库根 `skills/<skill_id>/`（对齐 `roles/` 内容包，
  不进 `lca` 包本体）。
- `ensure_bundled_skills(store)` 在 `resolve_skill_store()` 时幂等 materialize：
  缺包或 `content_hash` 变化则重装。
- skill_id：`officecli`。PDF 仍走 `anthropics-skills-pdf`。

### 三、镜像契约

- 钉版本（`OFFICECLI_VERSION`，默认见 Dockerfile ARG）。
- `OFFICECLI_SKIP_UPDATE=1`；产物写 `/mnt/data/outputs/`。
- contracts：`SANDBOX_PREINSTALLED_CLI_TOOLS` 含 `officecli`，与 prompt 对齐。

### 四、format 路由

| 格式 | 优先 skill | fallback |
|---|---|---|
| `.docx` / docx | `officecli` | `anthropics-skills-docx` |
| `.pptx` / pptx | `officecli` | `anthropics-skills-pptx` |
| `.xlsx` / excel | `officecli` | （数据分析仍用 pandas 预装包，可不激活 skill） |
| `.doc` legacy | `officecli`（转/处理策略见 skill） | `anthropics-skills-docx` |
| `.pdf` | `anthropics-skills-pdf` | — |

## 后果

- 正向：Office 创建/编辑统一 CLI；自愈 JSON；与 Onlyboxes terminal 平面一致；
  skill 可版本升级而不改 Tool 面。
- 负向：terminal 镜像体积增加；需运维重建镜像；screenshot 模式依赖浏览器
  时另开能力（默认 skill 不强制 screenshot）。
- 测试：`tests/test_format_routing.py`、`tests/test_officecli_plane.py`。

## 关联

- ADR-0044 沙箱适配器
- ADR-0048 操作技能库
- ADR-0050 Run-Bound Sandbox Runtime
- ADR-0051 Run Workspace Plane
