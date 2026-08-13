# AGENTS.md — LCA Framework

## 工程哲学

**不打补丁，追问前提。** 遇到不合理的代码，先问：是机制本身有问题，还是在垃圾机制上做修补？
- 看到 if/else 链 → 问"是不是缺了一个注册表或策略模式"
- 看到重复逻辑 → 问"是不是抽象层没提对"
- 看到 workaround → 问"被绕过的东西该不该存在"
- 看到过深的调用链 → 问"是不是职责分错了"
- 主动清理死代码、废弃别名、过渡方案——vulture 只是兜底，人工判断优先
- 有更好的架构就提出来，不要沉默地往旧设计里塞新代码

## 架构约束

五层单向依赖：`contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent`
`layer4_app` 是组合根，下层禁止反向 import。由 `lint-imports` 强制执行。

## 验证（按影响范围跑，不要默认全量）

全量慢在 `pytest` 的 `--cov=lca`。默认按 blast radius 选跑；说不清影响、改了契约/分层/公共 API、或准备提交时再升到全量。pre-commit 会再跑 ruff / lint-imports / mypy / vulture 等，**不含 pytest**。

### 默认循环

```
uv run ruff check --fix <改动路径> && uv run ruff format <改动路径>
uv run pytest --no-cov <对应测试> -q
```

对应测试：同名 `tests/test_<模块>*.py`，或对改动符号 `rg` 到 `tests/`。`gateway/runs/` → `tests/test_run_*.py`。一次改多处就并上相关测试文件，不要为了省事改跑全量。

### 影响范围

| 改了什么 | 必跑 | 再加 |
|---|---|---|
| 仅 `docs/`、`roles/`、注释 | 无 | — |
| 仅测试 | ruff 改动路径 + 这些测试 `--no-cov` | — |
| 实现细节（单模块、无公共 API 扩散） | ruff + 对应测试 `--no-cov` | 签名/类型变了 → `uv run mypy lca/<包>` |
| 新增/挪动 import、挪模块 | 上一项 + `uv run lint-imports` | 分层/组合根 → `tests/test_layer_boundary.py` `tests/test_architecture*.py` `tests/test_refactor_guards.py` |
| `gateway/`、`deploy/lobehub/patches/` | ruff + `tests/test_run_*.py` / `tests/test_gateway*.py` / `tests/test_lobehub*.py` 等对应文件 `--no-cov` | 改 patch 源后 `patch_lobehub.py apply --reset`（不要直接改 `lobehub-ui/`） |
| 删改被多处引用的符号 | 对应测试 + `uv run vulture lca --min-confidence 80` | 引用面大 → 全量 pytest |
| `contracts/`、Protocol、跨层公共签名、`pyproject.toml`、importlinter、注册表/枚举/journal catalog | 全量 | — |

层向上传染：改 `contracts` 视为全仓库；改 `layerN` 公共面至少覆盖本层测试和直接上层调用方，不要只跑被改文件的单测。

### 全量（提交 / PR / 升级条件触发；顺序不可乱）

```
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

`real_llm` 默认不跑，除非明确要求。声称通过前必须贴出所跑命令；局部绿不能写成「流水线已过」。

## 编码规范

- 方法 ≤200 行，文件 ≤1500 行；超过就拆
- 公共接口必须类型标注；contracts 用 stdlib dataclass
- 层间只通过 Protocol 通信，同层通过依赖注入协作
- 禁止魔数、硬编码密钥、裸 `except Exception`、`print`
- 多种实现 → `Protocol` + 注册表；外部集成 → 适配器
- 不生成 TODO/FIXME 占位；structlog 替代 print
- 配置走 pydantic-settings / 环境变量

## 领域语言

- `Agent`：单角色；`Team`：members + **恰好一种**协作机制
- 有主导者：`Team(lead=TeamLead.board(pm))` — mandate: `routing | consult | board`
- 无主导者：`Team(coordination=Pipeline()|FanOut()|PeerRelay()|PeerSwarm()|Debate()|Graph(...))`
- `lead.mandate` 与 `coordination` 禁止并存
- 场景 YAML 见 `tests/fixtures/team_scenarios/`，加载用 `tests/support/scenario_loader.py`

## 关键路径速查

| 关注点 | 位置 |
|---|---|
| Prompt 模板 | `lca/layer1_cognitive/brain/prompts/*.md` |
| 可观测性 | ADR-0037 Journal-as-Truth；`record()` / `span()` / `traced()` |
| 真实 LLM 测试 | `uv run pytest -m real_llm -v`（需 `LLM_API_KEY`） |
| 本地探针 | `uv run python scripts/run_team_mode.py` |

## 禁止事项

- 不绕过 pre-commit（`--no-verify`）
- 不让 contracts / layer0~3 import layer4_app
- 不直接改 `lobehub-ui/` 里的文件——改对应的 patch 源（`deploy/lobehub/patches/`），再 `patch_lobehub.py apply --reset`
