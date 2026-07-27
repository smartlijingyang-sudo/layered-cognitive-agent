# AGENTS.md — LCA Framework

## 架构约束（最容易被无意破坏，务必遵守）
五层严格单向依赖：contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent，
layer4_app 是组合根，可以依赖所有下层，但下层不能反向 import layer4_app。
这个约束由 import-linter 强制执行，见 pyproject.toml 中 [[tool.importlinter.contracts]]。

## 环境与依赖
- 包管理器统一用 uv，不要直接用 pip 改环境
- 安装依赖：uv sync --all-groups
- 新增依赖：uv add --group <lint|typecheck|test|security> <package名>

## 每次改完代码，必须依次跑完（顺序不能乱）
1. uv run ruff check --fix .
2. uv run ruff format .
3. uv run lint-imports        # 检查五层架构契约，最容易被跳过但最重要
4. uv run mypy lca
5. uv run pytest

## 代码风格
- 公共函数/类必须有类型标注
- lca/contracts 下的模型正在从 dataclass 迁移到 pydantic.BaseModel，迁移期间保持字段名和方法签名不变
- 禁止硬编码 API Key / Token，一律用环境变量，通过 pydantic-settings 注入配置

## 禁止事项
- 不要在 --no-verify 情况下绕过 pre-commit 提交
- 不要让 contracts / layer0~3 import layer4_app
