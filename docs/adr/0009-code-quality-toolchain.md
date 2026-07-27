# ADR-0009: 代码质量工具链

## 状态
Accepted

## 背景
LCA 已有 import-linter 五层架构契约（ADR-0001）写在 `pyproject.toml` 中，但缺少依赖声明与 CI/钩子执行，等于"纸面契约"。同时项目仅有 ruff 依赖、零配置，无类型检查器、无 pytest 依赖声明、无 pre-commit 与 GitHub Actions。在 AI coding 场景下，跨层 import、类型签名不匹配、硬编码密钥等问题无法被自动拦截。

## 决定
建立三层强制卡点：**编辑器实时反馈 → pre-commit → GitHub Actions CI**，工具选型如下：

| 类别 | 工具 | 作用 |
|---|---|---|
| Lint + 格式化 | ruff (check + format) | 替代 flake8/black/isort 等 |
| 类型检查 | mypy | CI/pre-commit 强制拦截；编辑器用 Pylance basic 模式做实时反馈 |
| 测试 | pytest + pytest-asyncio + pytest-cov | 单测、异步测试、覆盖率 |
| 架构治理 | import-linter | 强制执行 ADR-0001 五层单向依赖 + L4 组合根禁止反向依赖 |
| 安全 | ruff `S` 规则 + pip-audit + detect-secrets | 代码安全模式 + 依赖漏洞 + 硬编码密钥 |
| 代码卫生 | vulture | 死代码扫描（Protocol 桩文件排除） |
| 包管理 | uv | 依赖分组：lint / typecheck / test / security |
| AI 协作 | AGENTS.md | 告知 agent 每次改动后必须跑的五条命令 |

依赖通过 `[dependency-groups]` 分组，支持 `uv sync --group lint` 按需安装。

首版 ruff 配置对中文内容做了 pragmatic 调整：`RUF001/002/003`（全角标点）和 `TC001/003`（TYPE_CHECKING 强制）暂 ignore，待存量清理后再逐步收紧。

`OpenAICompatAdapter` 对 `openai` 包做 lazy import，使核心测试在无可选依赖时仍可运行。

## 后果
- 每次 push/PR 自动跑 ruff + import-linter + mypy + pytest + pip-audit + vulture，架构契约从"写在文档里"变为"每次提交强制执行"。
- 本地需执行 `uvx pre-commit install` 启用提交前卡点；`--no-verify` 绕过仅能在本地生效，CI 仍会拦截。
- mypy 当前为 non-strict 配置（`disallow_untyped_defs = true` 但 tests 豁免）；contracts 迁移到 pydantic v2 后需启用 `pydantic.mypy` 插件。
- vulture / interrogate 中 interrogate（docstring 覆盖率）首版未接入 CI，后续按需补充。
- Astral `ty` 类型检查器待 1.0 稳定且 pydantic 支持完善后，可低成本的替换 mypy。

## 关联 ADR
- Supersedes: 无（新增能力，不推翻已有架构决定）
- Related: [ADR-0001](0001-five-layer-separation.md)（import-linter 契约来源）
