# ADR-0120: 退役 DSH (DeepSeek Harness) driver 集成路径

- Status: Accepted (2026-08-31)
- Supersedes: ADR-0083 (DeepSeek Harness 插件布局实施计划)
- Decision: 删除 DSH 作为 LCA 执行目标路径。前端执行目标收窄为 `auto` / `local` (用电脑) / `sandbox` (云沙箱) / `device` (其他物理设备);`'dsh'` 选项、运行时、SDK、配置、文档全部退役。

## Context

### 历史
- 2026-08 至 2026-08,DSH 一度作为 LCA 的独立 driver 被设计并部分实现,经 `lca/infrastructure/comparison/dsh_driver/` 驱动 sandbox-user 侧的 DeepSeek Harness SDK。前端 LobeHub UI 暴露"用 DSH"选项。
- ADR-0083 给出 DSH 插件布局实施计划;ADR-0115 kernel/transport 边界收敛 + ADR-0117 env 白名单 + ADR-0103 §2 软锁面收紧后,DSH 与 Cognitive Runtime 的桥接价值已降低。
- LCA 已有等价执行路径:`local` (sidecar 用电脑) 与 `sandbox` (云沙箱)。两者覆盖 DSH 的所有使用场景。

### 现状(2026-08-31)
- DSH 运行时代码已迁到 `lca/infrastructure/comparison/dsh_driver/`(原 `lca/infrastructure/dsh/`),共 20 个文件。
- Gateway 适配层:`lca/plugins/transport/webserver/handlers/runs/dsh/execute.py` + `lca/plugins/transport/device_gateway/streaming_dsh_runtime.py`。
- Contracts:`lca/contracts/protocols/runtime/infra.py` 中保留了 `DshRuntime` Protocol(标注"Backwards-compat shim — DSH was removed on main")。
- Env 白名单:`BOOTSTRAP_PREFIXES` 中含 `"DSH_"` 前缀。
- UI:LobeHub patch `execution_target.py` 把 `DeviceExecutionTarget` union 加上 `'dsh'`;UI 提供"用 DSH"选项。
- 部署:`deploy/dsh/{README.md, install-dsh-sdk.sh, requirements-dsh.txt}`。
- 测试:`tests/lca/infrastructure/env/test_layered.py` 中有 `test_dsh_migration_prefix_allowed` 等。
- 文档:多份 design / spec / ADR / 历史文档涉及 DSH。

### 用户决定
- 前端只保留沙箱与电脑两个执行目标(实际保留 `auto`/`local`/`sandbox`/`device` 四种,`'dsh'` 删除)。
- 全量一次性清理(代码 + 配置 + UI + 部署 + 测试 + 文档)。
- DSH 文档章节从 design/spec/ADR 中全部清干净,不留"历史参考"脚注。

## Decision

1. **删除运行时核心**:移除 `lca/infrastructure/comparison/dsh_driver/`(20 文件)与 Gateway 适配层(`runs/dsh/`、`device_gateway/streaming_dsh_runtime.py`)。
2. **删除 Contracts**:`lca/contracts/protocols/runtime/infra.py` 中的 `DshRuntime` Protocol 及 `lca/contracts/protocols/__init__.py` 中的对应导出。`lca/contracts/protocols/README.md` 同步更新。
3. **删除 Env 前缀**:`lca/infrastructure/env/bootstrap.py` 的 `BOOTSTRAP_PREFIXES` 去掉 `"DSH_"`。
4. **删除共享函数**:`lca/infrastructure/attachment/prompt.py` 中的 `render_dsh_workspace_context`。
5. **删除 UI 选项**:LobeHub UI patch 把 `DeviceExecutionTarget` union 还原为 `'auto' | 'device' | 'local' | 'none' | 'sandbox'`;`execution_target` 行为改为只渲染 `auto` / `local` / `sandbox` / `device`;`LcaRunDriver.ts` 移除 `'dsh'` 分支;`CUSTOMIZATIONS.md` 同步。
6. **删除部署脚本**:`deploy/dsh/` 整目录删除。
7. **删除测试断言**:`test_dsh_migration_prefix_allowed` / `BOOTSTRAP_PREFIXES` 中 `"DSH_"` 项 / `scenario_harness.py` 中 `lca-loop-dsh-bridge` 与 `lca-dsh-bridge` plugin id 引用。
8. **删除 package contracts**:`pyproject.toml` 中 `[tool.lca.package_contracts."lca.infrastructure.dsh"]` 与 `[tool.lca.package_contracts."lca.infrastructure.comparison.dsh_driver"]` 整块删除。
9. **删除文档**:`docs/design/2026-08-14-deepseek-harness-integration-analysis.md` 与 `docs/design/2026-08-15-dsh-path-a-deep-research.md` 整篇删除;`docs/design/*` 与 `docs/specs/*` 中所有 DSH 段落整段删除。
10. **关闭 ADR-0083**:ADR-0083 标注 "Superseded by ADR-0120";`docs/adr/README.md` 索引同步。

## 不变量

DSH 退役后,以下不变量在 LCA 内部生效:

1. **执行目标闭集**:`'auto' | 'device' | 'local' | 'sandbox' | 'none'`(5 个值);`'dsh'` 不再存在。
2. **不变量 C1 闭集**:改变执行目标闭集必须先有 ADR。
3. **不变量 C6 最小化**:不重新引入 DSH driver;不重新引入 `DshRuntime` Protocol;不重新引入 `"DSH_"` env 前缀。
4. **Plugin Manifest 闭集**:`loop-dsh` / `lca-loop-dsh-bridge` / `lca-dsh-bridge` plugin id 不可再用。

## Consequences

### 正向
- 执行目标更清晰,前端 UI 不再有"用 DSH"与"用电脑"两个等价选项;`lca/infrastructure/comparison/` 子包精简。
- DSH_SESSION_C / DSH_ env 不再透传到子进程;`sandbox-user` 端 daemon 不再需要单独的 DSH venv。
- `pyproject.toml` 中两个 stale `package_contracts` 块清理,`check_package_contracts` 门禁不会误报。
- `importlinter` `kernel-domain-isolation` 与 `transport-isolation` 两条合约不再需要为 DSH 例外。

### 风险与缓解
| 风险 | 缓解 |
|---|---|
| 旧用户 localStorage 仍有 `executionTarget: 'dsh'` | UI patch 中 `lcaDisplayTarget` 通过白名单过滤,只接受 `'auto'/'local'/'device'/'sandbox'`,旧的 `'dsh'` 值会回落到 `'auto'`;不会报错 |
| `tests/support/scenario_harness.py` 引用了不存在的 plugin id | 删除对应行;scenario_harness 是测试支持代码,真实运行不依赖 |
| DSH 历史 commit/PR 引用 | commit 历史无法修改;ADR-0120 明确 "Supersedes 0083" |
| `device_gateway/streaming_dsh_runtime.py` 死引用 `hub.run_dsh_turn` | 整个文件删除,死引用随文件消失 |
| `DshRuntime` Protocol 删除后旧 import 残留 | 通过 `ruff` / `mypy` / 全量 `pytest` 捕获;importlinter 报则按合约白名单更新 |
| 已 patch 过的 lobehub UI 源码中残留 `'dsh'` 选项 | `execution_target.py` patch 的 reverse 路径会清理它;新部署直接走干净源码 |

### 兼容策略
- 不保留任何 `'dsh'` 字面量兼容路径。
- 不保留 `DshRuntime` Protocol 兼容 shim。
- 不保留 `lca-loop-dsh-bridge` / `lca-dsh-bridge` plugin id。

## 借鉴保留

借鉴 deepseek 的非 DSH 部分继续保留,与本 ADR 无关:
- `lca_kernel/` 借鉴 deepseek `app-boot` / `host-webserver` 的 BOOTSTRAP / lifecycle / composeEntries 模式
- `BOOTSTRAP_NAMES` / `BOOTSTRAP_PREFIXES` 借鉴 deepseek `BOOTSTRAP_NAMES` 模型
- `lca/plugins/transport/webserver/` 借鉴 deepseek `host/webserver` 的 register/dispose 模式
- LLM provider 列表中 `deepseek-chat` / `deepseek-reasoner` 模型名

## Implementation

执行计划见 `~/.grok/sessions/.../plan.md`(2026-08-31)。

## 验证矩阵

按 `AGENTS.md §6` 走完整流程:

```sh
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
scripts/check_kernel_boundary.py
# importlinter: kernel-domain-isolation + transport-isolation
```

具体预期:
| 检查 | 预期 |
|---|---|
| `ruff check .` | 0 error |
| `lint-imports` | 0 违反 |
| `mypy lca` | 0 error(若原本有 0) |
| `pytest` | 全绿;`test_dsh_migration_prefix_allowed` 已删,`test_bootstrap_prefixes_is_tuple_with_minimum_coverage` 仍过 |
| `vulture lca --min-confidence 80` | 不报 DSH 相关 dead code |
| `check_kernel_boundary.py` | 通过(已删 dsh_driver 包) |
| importlinter 两条合约 | 通过 |

## 回退方案

若用户在大规模改动中途决定保留 DSH,可分阶段回退;每个 layer 是独立 commit。详见 plan.md §10。
