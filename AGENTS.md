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

## 代码设计约束（AI Coding 必须遵守）

### 结构规模
- 单个方法不超过 200 行（不含空行和注释），超过则拆分为子方法或提取到独立模块
- 单个文件不超过 1500 行，超过则按职责拆分到同包下的新文件
- 按模块/职责划分目录，每个包只暴露 `__init__.py` 中显式导出的公共接口

### 内聚与耦合
- 高内聚：一个类/模块只做一件事，相关数据和行为放在一起
- 低耦合：模块间通过 Protocol / 接口通信，禁止直接依赖具体实现
- 可复用：公共逻辑提取为工具函数或基类，禁止跨模块复制粘贴

### 禁止魔数与硬编码
- 禁止裸数字/字符串字面量出现在业务逻辑中，必须用命名常量（`MAX_RETRIES = 3`）或枚举
- 配置项走 pydantic-settings / 环境变量，不要 `if env == "prod"` 硬编码
- 禁止 if/else 链做类型/状态判断——用枚举、标签字段、注册表或策略模式替代：
  ```python
  # BAD
  if provider == "openai": ...
  elif provider == "anthropic": ...

  # GOOD — 注册表 + 策略
  _registry: dict[str, type[LLMAdapter]] = {}
  def get_adapter(provider: str) -> LLMAdapter:
      return _registry[provider]()
  ```

### 设计模式优先
- 多种实现 → 策略模式（`Protocol` + 注册表）
- 跨 provider 适配 → 适配器模式（统一接口包装差异）
- 复杂构建 → Builder / Factory
- 事件通知 → 观察者 / 发布-订阅
- 处理链 → Chain-of-Responsibility（如 middleware、handler pipeline）
- 优先用声明式/数据驱动分发，少用命令式分支

### 接口解耦
- 层间依赖只通过 contracts 层的 Protocol / BaseModel 传递
- 同层模块间不直接 import，通过依赖注入（构造函数参数）获取协作方
- 新增外部集成（LLM provider、向量库、消息队列等）必须走适配器，不允许业务代码直接调用第三方 SDK

### AI Coding 额外约束
- 生成的代码必须可测试：纯函数优先，副作用隔离到边界，便于单元测试
- 不生成 TODO / FIXME 占位——要么实现，要么不写
- 不在生成代码中引入 `# type: ignore` 除非有注释说明原因
- 错误处理用显式的自定义异常类，不用裸 `except Exception`
- 日志用 structlog 结构化输出，不用 `print`
- 异步代码中不在热路径做同步阻塞调用，需要时显式标注并说明原因

## 禁止事项
- 不要在 --no-verify 情况下绕过 pre-commit 提交
- 不要让 contracts / layer0~3 import layer4_app
