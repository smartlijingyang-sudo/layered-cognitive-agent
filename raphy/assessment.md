# Raphy Assessment — Round 4 (2026-10-07 16:30, branch `raphy/arch-20261007-1630`)

ASSESS ONLY. 本轮按硬化版 `raphy-assess.md` 执行：读
`skills/improve-codebase-architecture/SKILL.md` → git log 热点定域 →
三区 friction walk（5 问必答，端到端精读非 grep）→ duplication 副扫描 →
self-grilling → stories 入 prd.json。

## Scope（YAGNI）

`git log --oneline -60` 热点（排除 raphy/ralph 与 iter style 扫荡）：
- `lca/infrastructure/host_runtime/providers/user_cli.py` ×3（CLI 部署 + per-user daemon）
- `lca/infrastructure/observability/journal/step/narrative_writer/*`（fold.py 216 行新动）
- `lca/harness/profile/plan/declarations.py` ×2（但已废弃 → ADR-0115，转看同包 projection.py）
- `scripts/snapshot_capability_tree.py` + `tests/architecture/test_capability_snapshot.py`
  （snapshot scanner，上一轮刚加 `_register_composer_plugin` 识别 ——
  读后判定为工具脚本+快照测试，属一次性胶水，无模块可深挖，丢弃）

禁区遵守（`raphy/progress.txt` 顶部 `## Codebase Patterns`）：
ralph Round 2 领地、lca-1000 领地、iter lanes 的 DelegationCacheHit 接线区、
`gate_chain_strategy.py`（绝不动），全部避开。

选定三区：**A. `lca/infrastructure/host_runtime/`**
（providers + environment）、**B. `journal/step/narrative_writer/`**、
**C. `lca/harness/profile/plan/`**。

## Friction walk

### 区 A — host_runtime（精读：providers/__init__.py、shared.py、user_cli.py、environment.py、cli/services/daemon/daemon.py:1-150、cli/services/__init__.py:25-48、cli/service/service.py:184-196）

**Q1. 理解一个概念要在多少小模块间跳？**
理解"connect daemon 的生命周期"要在三处跳：`CLIProvider.start_daemon/stop_daemon`
（host_runtime/providers/user_cli.py）、`DaemonService.start/stop`
（cli/services/daemon/daemon.py）、`HostEnvironment.provision/destroy`
（environment.py 74 行又各自 `CLIProvider(self.config, user)` 一份实例）。
同一进程（`node dist/index.js connect`）的两套生命周期实现，
只靠一句注释（daemon.py:33-36 "Single source shared by …"）和
一个**私有**常量 import 维系关系。

**Q2. 哪些模块 shallow？**
`CLIProvider`（222 行）身兼两职：CLI artifact 构建部署（npx tsc、sudo cp、
wrapper 脚本）+ per-user daemon 生命周期（pid 文件、pgrep、start.sh）。
interface（provision/status/heal）承载两个正交关注点，depth 低。
`DaemonService` 才是正牌 daemon owner（RA-006 单活不变量接缝 `_kill_existing`
落在这里）。

**Q3. 为可测性抽出的纯函数，bug 藏在调用处？**
RA-007 把 `render_start_script` 抽成纯函数（cli/services/daemon/start_script.py），
但 `CLIProvider._write_start_script` 在调用方**另写了一份 inline 的**
connect start.sh 模板（不同参数：`--gateway/--workspace/--token`）。
两份 start script 模板各自演化，drift 藏在调用处。
更严重：`CLIProvider` 自身**零测试**（tests/ 下无 CLIProvider 引用），
它的 daemon 路径完全不受测试钉住。

**Q4. 紧耦合模块的 seam 泄漏？**
`user_cli.py:13`：`from lca.infrastructure.cli.services.daemon.daemon import _CONNECT_PROC_PATTERN`
—— 跨接缝 import **私有**名（前导下划线）。host_runtime 本应经正式接缝
消费 cli 层的 daemon 契约，现在是靠私有常量"偷渡"。
`_CONNECT_PROC_PATTERN` 的注释自称 "single source"，但 single 的只是字符串，
不是行为。

**Q5. 哪些部分测不到 / 只能绕过 interface 测？**
`CLIProvider.provision/start_daemon` 经 `Provider.run/run_sudo` 直接
`subprocess.run` + sudo，无注入点；interface（provision→bool）不经过
test surface。对比 `DaemonService` 有
test_daemon_kill_existing / test_daemon_stop_uses_sudo /
test_daemon_start_script 三组测试钉住。→ **testability gap 实锤**。

**区 A 结论**：产出 RA-014（Strong）。附带发现：`CLIProvider._pid_alive`
（212-219 行，os.kill(pid,0)/ProcessLookupError/PermissionError）
是 `lca/infrastructure/cli/service/service.py::pid_alive`（184-196 行，
同语义）的私有复刻 —— daemon.py 已从 service import 公共版，
只有 CLIProvider 在用私有复刻。另 `_report_kernel_serve_status`
用 `curl -sf` 子进程探活，而 DaemonService 用 `http_ready` seam ——
同一"kernel_serve 可达性"概念两套探活实现。

### 区 B — narrative_writer（精读：sections.py、fold.py、writer.py、__init__.py 全文）

**Q1.** 理解"一步的 narrative"需读 writer（编排）+ sections（5 原语）+ fold
（5 fold 章节）三文件，但每文件职责单一、docstring 写明分工，
是 ADR-0164/0185 落地后的**刻意拆分**，非 sprawl。
**Q2.** `_short/_format_duration/_format_ts` 是小而深的格式化 helper，
被 sections 与 writer 共享；deletion test：删掉会散落截断逻辑到各渲染器 →
concentrates，通过。
**Q3.** `render()` 显式声明为纯函数（"测试 / CLI 直接 print 用"），
fold 失败走 `_safe_fold` 吞异常降级 N/A —— 真实行为（优雅降级）就在模块内，
且 fold_provider seam 可注入 mock。无"调用处藏 bug"。
**Q4.** `FoldedModelVisible` 只在 TYPE_CHECKING 下 import；writer 经
`spine_filename_for_run` 命名 seam 找 spine，无泄漏。
**Q5.** render 纯函数 + fold_provider 可注入 → 可测性好。
**区 B 结论**：无 friction，不开 story（读了 4 文件，问题均不适用）。

### 区 C — harness/profile/plan（精读：declarations.py、projection.py、immutable.py、plugin_metadata.py）

**Q1.** declarations.py 顶部即声明废弃（ADR-0115 → lca_kernel.declarations），
跳过；projection.py 是"已解析 Profile 的唯一只读 seam"，
`ResolvedProfileProjection.build` 一次规范化 11 个字段，下游只消费投影 →
深模块，无需跳读。
**Q2.** `plugin_metadata.py`（37 行，单函数）看似 thin，但 docstring 声明
它是"旧 setup.meta vs 模块级 setup.plugin_meta 合并优先级"的统一 seam，
调用方有 projection.py 与计划编译多处；deletion test：删掉会把
"模块级覆盖 setup"优先级规则散到各调用方 → concentrates，通过，保留。
**Q3/Q4.** 无为可测性抽取的纯函数；`_configuration_values` 的
model_dump/Mapping 双形态是刻意的兼容 seam，非泄漏。
**Q5.** frozen dataclass 投影，interface 即 test surface，可测。
**区 C 结论**：无 friction，不开 story。

## Duplication 副扫描（friction walk 之后）

- `_pid_alive` 私有复刻（user_cli.py:212）vs `service.pid_alive`：2 站点，
  并入 RA-014 acceptance（按"converge N identical X" idiom 处理）。
- `user_cli.py` 内两处 tempfile 舞蹈：`_ensure_wrapper`（156-166）与
  `_write_start_script`（168-186）——"NamedTemporaryFile 写 → sudo cp →
  unlink → chmod/chown" 同一仪式两遍。one adapter=hypothetical, two=real →
  真接缝。产出 RA-015。
- `run_sudo(["bash","-c", f"echo '…' > …"])` 3 站点（shared.py ×2、user_cli.py ×1）：
  机械度够但语义是"特权写文件"而非 tempfile-stage，与 RA-015 不完全同形；
  记为 RA-015 的可选扩展，不强制。
- 丢弃：`StatusReport.fail` → `ItemStatus.MISSING` 而 `ERROR` 枚举闲置 ——
  语义小瑕疵，无行为影响，无 story。

## 候选表

| # | Files | Problem | Solution | Benefits（locality+leverage） | Strength |
|---|-------|---------|----------|-------------------------------|----------|
| RA-014 | `lca/infrastructure/host_runtime/providers/user_cli.py`、`lca/infrastructure/cli/services/daemon/daemon.py`、`lca/infrastructure/cli/service/service.py`、`lca/infrastructure/host_runtime/environment.py` | 同一个 connect daemon 有两套生命周期实现：`DaemonService`（lca-ops 路径，有 RA-006 单活接缝与 3 组测试）与 `CLIProvider.start/stop_daemon`（host_runtime 路径，零测试、私有复刻 `_pid_alive`、curl 探活）。两者只靠 import 私有常量 `_CONNECT_PROC_PATTERN` 维系；`CLIProvider` 身兼部署+daemon 两职，interface 浅。RA-006 的单活不变量在 CLIProvider 路径上不生效。 | DaemonService 成为 daemon 生命周期的唯一 owner；CLIProvider 的 daemon 部分经显式接缝委托（composition），只保留 artifact 部署；`_CONNECT_PROC_PATTERN` 去私有化或移入 cli.service 公共面；`_pid_alive` 删除改调 `service.pid_alive`；kernel_serve 探活收敛到 `http_ready` seam | locality：daemon 生命周期语义（含单活）只活在一处，修 invariant 不用改两处；leverage：后续 daemon 行为变更（重启策略、健康检查）自动对两条调用路径生效；测试：CLIProvider 的 daemon 路径首次可经委托 mock 被测试钉住 | **Strong** |
| RA-015 | `lca/infrastructure/host_runtime/providers/user_cli.py` | `_ensure_wrapper` 与 `_write_start_script` 各写一遍 tempfile→sudo cp→unlink→chmod/chown 特权文件仪式 | 抽 `_stage_privileged_file(content, dest, *, owner, mode)` 小 seam，两处委托；3 处 bash echo-write 记为可选扩展 | locality：特权提升仪式（含 unlink 纪律这个安全面）集中一处；leverage：以后加"写前备份/写后校验"只改一处 | Worth exploring |

## Self-grilling

### RA-014
- **Constraints**：`lca-ops` 的 daemon start/stop/status 命令行为不变；
  `HostEnvironment.provision/destroy` 外部行为不变（bool 返回、日志行）；
  RA-006 单活不变量语义保留；不违反 ADR-0119 决定 4（services 由 lca-ops
  管理 —— RA-014 正是落实它：host_runtime 不应再私设第二套 daemon 管理）。
- **Dependencies**：`HostEnvironment` 调 `CLIProvider.start/stop_daemon`
  与 `heal`；`build_registry` 调 `DaemonService`；测试钉住
  DaemonService（kill_existing/stop_uses_sudo/start_script 三组），
  CLIProvider 零测试 → 动它无回归风险。
- **Shape of the deepened module**：`CLIProvider` 瘦身为纯部署 provider
 （provision/status 的 deployed 检查）；daemon 生命周期经
  `DaemonService`（或其抽出的 lifecycle seam）委托；
  `_CONNECT_PROC_PATTERN` 去下划线成为共享常量（或进 cli.service 公共面），
  私有跨接缝 import 消失。
- **Test survival**：三组 daemon 测试继续全绿；新增测试钉
  `CLIProvider.heal` 经委托路径仍工作（mock DaemonService）。
- **Deletion test**：删掉 CLIProvider 的 daemon 一半 → 生命周期复杂度
  集中到本就拥有接缝+测试的 DaemonService（concentrates）；CLIProvider
  interface 变深。 verdict：**通过，该存在**。

### RA-015
- **Constraints**：tempfile+cp+unlink 原子性、chmod/chown 语义、sudo 密码流不变。
- **Dependencies**：仅 user_cli.py 内部两处调用。
- **Shape**：`_stage_privileged_file(content: str, dest: Path, *, owner: str | None, mode: str | None)`；
  两处委托；echo-write 3 站点可选后续收敛。
- **Test survival**：无现有测试；新测试用 fake run_sudo 钉住调用序列
  （cp→chmod/chown→unlink）。
- **Deletion test**：删掉 helper → 特权仪式散回两处（concentrates）。 verdict：**通过**。

## 丢弃（有证据）

1. narrative_writer 三区：ADR-0164/0185 落地后的刻意拆分，pure render +
   fold_provider seam，可测，无 friction。
2. `plugin_metadata.py`：有文档的 legacy 合并 seam，多调用方，
   deletion test 通过 → 保留。
3. `Provider.run_sudo` 读相对路径 `.lobehub-stack/sudo.pass`
   （cwd 隐式契约）：无测试钉住、无已证 bug → speculative，不开 story，
   记 observation。
4. `ItemStatus.ERROR` 枚举闲置 / `fail()`→MISSING：语义小瑕疵，无行为影响。
5. `scripts/snapshot_capability_tree.py`：工具胶水+快照测试，无模块可深挖。

## Top recommendation

先做 **RA-014**：它是本轮唯一的 Strong —— 两套 daemon 生命周期是真实的
行为分叉风险（RA-006 的单活接缝只保护了一条路径），且 `CLIProvider`
零测试意味着重构无回归包袱；做完后 `CLIProvider` 回归为纯部署 provider，
interface 深度立刻上升。RA-015 是同文件内的顺手收敛，可在 RA-014 之后做。

Assessment complete: 2 stories written, top is RA-014.
