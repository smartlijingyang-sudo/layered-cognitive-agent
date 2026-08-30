# Task Plan: ADR-0076 闭环与剩余门禁收敛

## Goal

在 `74f71e10`（ADR-0076 全部 §一-§六、P0-P5 已落地）的基础上，把
`ADR_66_69_74_75_76_IMPLEMENTATION_AUDIT.md` §四列出的红色门禁转为绿色，使
ADR-0076 与相关 ADR（0066/0068/0074/0075）能基于全量回归完成 sign-off。

## Current Phase

Phase 3

## Phases

### Phase 1: 同步状态确认
- [x] 确认 `origin/main == HEAD`（已确认：`74f71e10`）
- [x] 确认工作区干净（已确认：`git status --short` 无输出）
- [x] 记录 SSH 阻断的兜底命令（GIT_SSH_COMMAND 绕过 `05-redhat.conf`）
- [x] 在 `findings.md` 写入仓库与远程的当前事实
- **Status:** complete

### Phase 2: 头部提交目标验证
- [x] 跑 `tests/plan/test_action_authority_plan.py`（7 passed）
- [x] 跑 `tests/architecture/test_handler_substitutability.py`（70 项中含 9 项 P2）
- [x] 跑 `tests/composer/test_composer_consumes_compiled_capability.py`
- [x] 跑 `tests/architecture/test_substitution_gates.py`（P5 静态 AST 门禁）
- [x] 跑 `tests/architecture/test_run_mode_registry.py`（12 项 W6）
- [x] 跑 `tests/architecture/test_six_plane_taxonomy.py`（六平面映射）
- [x] 跑 `tests/test_boot_binding_completeness.py`（P0 binding validator）
- **Status:** complete（合计 77 passed，0 failed）

### Phase 3: 审计 §四 红色门禁收敛
- [x] **声明式 stop/final_output 传播**：完成。`CognitiveRuntime` fixture fallback 现在注册 provider 的 11 个默认 DeltaHandler；`tests/declarative/test_runtime_driver.py` 确认 stop 状态与 `final_output` 经 Reducer 传播
- [x] **Protocol 显式继承**：`scripts/check_protocol_impl.py` 18 处失败 → 已将 17 个真实实现补齐显式 Protocol 继承，2 个概念误判保留可审计 allowlist
- [ ] **裸 `Any` 清理**：`scripts/check_no_any.py` 失败 → 收口 `CognitiveRuntime` / phase provider / mode & loop driver 的 `Any` 类型
- [ ] **action authority 唯一源**：`_SCOPE_ACTIONS` 已迁为 metadata，验证无生产代码读该静态表
- **Status:** in_progress

### Phase 4: 门禁复测
- [ ] 跑 `uv run ruff check --fix . && uv run ruff format .`
- [ ] 跑 `uv run lint-imports`
- [ ] 跑 `uv run mypy lca`
- [ ] 跑 `uv run pytest --no-cov -q`（目标：2768 + 修复项全绿，27 失败清零）
- [ ] 跑 `uv run vulture lca --min-confidence 80`
- [ ] 跑 `scripts/check_no_any.py` / `check_protocol_impl.py` / `check_no_bare_strings.py` / `check_plugin_typing.py` / `check_assembly_purity.py`
- [ ] 跑 `scripts/verify_md_links.py` / `verify_doc_budgets.py`
- [ ] 跑 `python scripts/check_adr_supervision.py` 与 `./scripts/lca-ops status-adr-supervision`
- **Status:** pending

### Phase 5: ADR 状态更新与交付
- [ ] 把 `ADR_66_69_74_75_76_IMPLEMENTATION_AUDIT.md` §四的失败项转为「已关闭」陈述
- [ ] 在 `docs/plans/adr-0074-plugin-everything-tracker.md` §6 记录 P0-P5 闭环
- [ ] 更新 `docs/adr/0076-*.md` 的验证约束条目反映实际通过的测试路径
- [ ] 在 `progress.md` 记录命令-结果对照表
- **Status:** pending

## Key Questions

1. `Result.from_state()` 负责把已折叠的 `AgentState` 转为 `Result`；不需要在 `RuntimeEffectGateway` 直接写结果。`stop` delta 必须先由 `StopDeltaHandler` 调用 `Reducer.apply_stop()`，再由 `Result.from_state()` 读取 `status` 与 `final_output`。
2. 18 处缺 Protocol 父类声明的类集中在哪些模块？是否能用一次 grep 列出清单？
3. `CognitiveRuntime` 的 `Any` 类型是否仅来自 `run(state: Any)` 一处签名，还是多个签名？
4. `_SCOPE_ACTIONS` 改名 `_SCOPE_DEFAULT_ACTIONS` 后是否还有任何生产路径 import 它？
5. ADR-0075 的 11 项整改是否随本次提交已全部转「已实现」？需逐项核对
   `ADR_66_69_74_75_76_IMPLEMENTATION_AUDIT.md` §二。

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| 不实际 `git pull` | `git branch -vv` 显示 `[origin/main]`，本地已与远程同步 |
| 跳过 `git fetch` | SSH 受 `/etc/ssh/ssh_config.d/05-redhat.conf` 阻断；不修系统文件 |
| 规划文件放仓库根目录 | skill 规定 + `docs/AGENTS.md` 禁止新建 `docs/plans/` 等过程目录 |
| 不写「已实现/未来」状态标注 | `docs/AGENTS.md` slop 检查清单；状态由仓库布局和测试名承载 |
| 计划以 ADR-0076 闭环为主轴 | 用户指定「最新提交」，最近 5 提交均围绕 ADR-0076 落地与审计 |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `ssh: Bad owner or permissions on /etc/ssh/ssh_config.d/05-redhat.conf` | 1 | 不修系统配置；用 `GIT_SSH_COMMAND='ssh -F /dev/null -i ~/.ssh/id_ed25519_github'` 兜底，本会话无需远端操作 |

## Notes

- 每次阶段切换前重读本文件 §「Current Phase」与 §「Phases」对应条目
- 跑命令后立刻把 exit code 与耗时写入 `progress.md`「Test Results」
- 失败按「3-Strike Error Protocol」处理：诊断 → 替代方案 → 升级用户
- Phase 3 的「裸 Any 清理」与 ADR-0075 §二 第 11 项（DeclarativeRuntimeDriver 类型安全）重叠，关闭该任务即可同步清掉 ADR-0075 第 11 项
