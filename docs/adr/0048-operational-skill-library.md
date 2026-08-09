# ADR-0048: 操作技能库 — Role / Skill 分离 + 网络拉取

## 状态

Accepted

## 背景

LCA 已有 **角色库**（`roles/` + `RoleLibrary` + `TeamCaster`，ADR-0042）回答
「谁来做」——身份、记忆、组队时刻绑定。LobeHub / Anthropic Skills 机制回答
「怎么做」——纯操作知识，与 persona 无关，执行中按需拉取。

原 `specialized-document-generator` 等角色卡把操作知识焊进 backstory，导致：
- 非文档角色遇到「导出 PDF」时缺操作指南；
- 操作知识无法跨角色复用；
- 与 LobeHub「Market 下载 → activate → execScript」范式不对齐。

现有 `SkillRouter`（`cognition.py`）是 **Prompt 模板路由**，语义不同，不扩展其职责。

## 决定

### 1. 平行抽象：Operational Skill ≠ Role

| 维度 | RoleLibrary | SkillPackageStore |
|---|---|---|
| 回答 | 谁来做 | 怎么做 |
| 触发 | 组队 `TeamCaster.cast()` | 执行中工具调用 |
| 内容 | 身份 / 记忆 / 分工 | SKILL.md + 资源文件 |
| 存储 | `roles/`（内容包） | `~/.lca/skills/`（import 缓存） |

契约：`lca/contracts/protocols/operational_skills.py`

### 2. 网络 import 为主路径，本地目录为辅（缓存）

- **SkillImporter**（`HttpSkillImporter`）：从 LobeHub Market ZIP、GitHub 目录、
  ZIP URL、裸 SKILL.md URL 拉取并 materialize。
- **SkillPackageStore**（`DiskSkillPackageStore`）：content-addressed 安装树，
  `manifest.json` + `SKILL.md` + `resources/`。
- Market **search** 需鉴权；**download/detail** 公开可用。
  无鉴权时 `search_skill` 降级为搜本地已安装。
- 鉴权优先级（与 [LobeHub Skills Marketplace](https://lobehub.com/skills/skill.md) / `@lobehub/market-cli` 对齐）：
  1. `LCA_SKILL_MARKET_TOKEN` 静态 Bearer
  2. M2M：`LCA_SKILL_MARKET_CLIENT_ID`+`SECRET`，或 `MARKET_CLIENT_ID`+`SECRET`，
     或 `~/.lobehub-market/credentials.json`（`npx @lobehub/market-cli register` 写入）
  3. 自动 OAuth2 client_credentials + JWT assertion 换 access token 并缓存
- **Search 降级**：`GET /api/v1/skills?q=` 在部分 M2M token 下会 `invalid_token`
  （官方 CLI 亦复现）；失败时改走 `/api/v1/skills/identifiers` 本地关键词过滤
  （缓存 `~/.lca/skills/market_identifiers.json`，TTL 24h）。
- Agent prompt 内嵌自学习环：`search_skill` → `import_skill` → `activate_skill` → 执行。

环境变量（`LCA_SKILL_*`，pydantic-settings）：

| 变量 | 含义 |
|---|---|
| `LCA_SKILL_CACHE_DIR` | 安装缓存根，默认 `~/.lca/skills` |
| `LCA_SKILL_MARKET_BASE_URL` | 默认 `https://market.lobehub.com` |
| `LCA_SKILL_MARKET_TOKEN` | 静态 Bearer（可选，覆盖 M2M） |
| `LCA_SKILL_MARKET_CLIENT_ID` / `_SECRET` | M2M 凭证（可选） |
| `LCA_SKILL_MARKET_CREDENTIALS_PATH` | market-cli credentials.json 路径 |

### 3. 五个默认工具（`build_default_tools`）

| 工具 | 对标 LobeHub | 作用 |
|---|---|---|
| `search_skill` | searchSkill | 发现 skill |
| `import_skill` | importSkill / importFromMarket | 网络安装 |
| `activate_skill` | activateSkill | SKILL.md → LLM 上下文 |
| `read_skill_reference` | readReference | 读包内附属文件 |
| `run_skill_script` | execScript | 资源挂载进沙箱 + shell |

`run_skill_script` 仅在 Onlyboxes 配置时挂载（与 `run_sandbox_code` 同条件）。

激活 skill 记入 run-scoped `activation_scope`（contextvar），供 exec 解析最近 skill。

沙箱挂载：`/mnt/data/_skills/<skill_id>/…`（`SANDBOX_SKILL_MOUNT_PREFIX`）。

### 4. 与角色库关系

- **不替代**：专职文档角色仍可组队牵头；
- **解耦**：财务分析师执行中 `import_skill` → `activate_skill("pdf")` 即可，
  无需重新组队拉文档生成器。

### 5. 沙箱 baseline 同步（ADR-0044）

文档类预装包扩展：`python-docx`、`reportlab`、`fpdf2`、`pypdf`；
镜像加装 `fonts-noto-cjk`（与文泉驿并存）。运行时 pip 仍仅作 skill
`requirements.txt` 的 exec 兜底，不是主路径。

## 后果

- 正向：对齐 LobeHub 三层（store / activate / exec）；Role-Skill 语义清晰；
  网络拉取 + 本地缓存可离线复用已安装包。
- 负向：Market 搜索依赖可选 token；GitHub 目录 import 暂只拉 SKILL.md
  （资源需 Market ZIP 或后续 GitHub tree 递归）。
- 测试：`tests/test_operational_skills.py` 覆盖 zip 安全、磁盘 store、工具链；
  网络测试用 mock httpx。

## 已知妥协（Phase 1）

- 不做 embedding 检索；关键词 + Market API + 本地索引。
- 不支持 skill 间依赖声明。
- GitHub 多文件 skill 需 Market ZIP 或手动 import zip URL。
