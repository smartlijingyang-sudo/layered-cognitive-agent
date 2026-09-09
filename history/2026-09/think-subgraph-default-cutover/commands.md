# Commands — agent 重启 / 验证 / debug 一站式

所有命令都从仓库根目录执行。`./scripts/lca-ops` 入口暴露 8 个核心子命令,
这里只列与 think subgraph 切后最相关的 7 条。

## 1. 启动 / 重启 kernel

### 1.1 `kernel-restart`(最常用)

```bash
./scripts/lca-ops kernel-restart
```

**做的三件事**(ADR-0213 PR-3):
1. SIGTERM 旧 `lca_kernel serve` 进程
2. 等端口空(K6 `run_kernel_lifespan` LIFO dispose)
3. `KernelServeSpawner.run()` 用 5 步状态机拉起新 kernel
   (`preflight → start → port_bound → http_ready → plugin_ready`)

**默认 spawn argv**(从 `lca/infrastructure/cli/services/kernel/spawner.py:478`):

```text
sys.executable -m lca_kernel serve \
  --profile <KernelServeConfig.profile>   # 默认 profiles/web-standard.yaml
  --host    <KernelServeConfig.host>      # 默认 0.0.0.0
  --port    <KernelServeConfig.port>      # 默认 8765
  --allow-unknown-env
```

**期望输出(成功)**:

```text
运行模式 OK · kernel_serve profile=profiles/web-standard.yaml host=0.0.0.0 port=8765
To start, run (in another shell):
  uv run python -m lca_kernel serve --profile profiles/web-standard.yaml --host 0.0.0.0 --port 8765 --allow-unknown-env
[StageResult ok=True] ...   (各 stage 详细)
LCA kernel restarted (pid=<新 pid>, <duration>ms)
```

### 1.2 显式启动(前台)

```bash
uv run python -m lca_kernel serve \
  --profile profiles/web-standard.yaml \
  --host 0.0.0.0 --port 8765 \
  --allow-unknown-env
```

挂起到 Ctrl-C,默认走 `web-standard.yaml` → subgraph host。

## 2. 看启了什么(读加载清单)

### 2.1 `inspect-tree` — 完整 plugin Manifest

```bash
./scripts/lca-ops inspect-tree profiles/web-standard.yaml
```

**期望关键行**(422 个 plugin 全列,**只列与 think 相关的 7 个**):

```text
phase.think.standard               [active] kind=phase-executor layer=L2
  module=lca.plugins.loop.phase.think.standard.plugin
  provides: phase.think.standard

phase.think.subgraph.shortcut      [active] kind=phase-executor layer=L2
  module=lca.plugins.loop.phase.think.subgraph.shortcut.plugin
  provides: phase.think.subgraph.shortcut

phase.think.subgraph.route         [active] kind=phase-executor layer=L2
phase.think.subgraph.reason        [active] kind=phase-executor layer=L2
phase.think.subgraph.classify      [active] kind=phase-executor layer=L2
phase.think.subgraph.gate          [active] kind=phase-executor layer=L2

phase.think.subgraph_host          [active] kind=phase-executor layer=L2
  module=lca.plugins.loop.phase.think.subgraph_host.plugin
  provides: phase.think.subgraph_host
  config_from: entry_node←bundles/think-subgraph-host.yaml#config.entry_node,
              plan_ref  ←bundles/think-subgraph-host.yaml#config.plan_ref
```

**关键判读**:
- `phase.think.subgraph_host` 出现 = 切到位
- `phase.think.standard` 出现但**任何 phase graph 节点都不绑它** = 切生效的标准期望状态
- 缺任何一个 `phase.think.subgraph.*` = think-subgraph bundle 没被 profile 加载

### 2.2 `why-plugin <name>` — 看某个 plugin 的来源

```bash
./scripts/lca-ops why-plugin phase.think.subgraph_host --profile profiles/web-standard.yaml
```

**期望输出**:

```text
plugin: phase.think.subgraph_host
module: lca.plugins.loop.phase.think.subgraph_host.plugin
source: /home/lichao/.../bundles/think-subgraph-host.yaml
kind/layer: phase-executor/L2
provides: ['phase.think.subgraph_host']
requires: []
test_suite: tests/cognition/test_think_subgraph_parity.py
disabled: False
enables: (no dependents in DAG)
```

**看什么**:`source` 必须是 `bundles/think-subgraph-host.yaml`,否则说明绑定链断了。

```bash
./scripts/lca-ops why-plugin phase.topology.standard --profile profiles/web-standard.yaml
```

**期望输出**:`source` 必须以 `bundles/declarative-phase-graph.yaml+patch` 结尾
(`+patch` 后缀 = 走的是 `phase.topology.standard` 的 patch override,不是共享 bundle 原值)。

## 3. 看 think.main 绑到哪

```bash
./scripts/lca-ops why-plugin phase.topology.standard --profile profiles/web-standard.yaml
```

只这一步不够 — `why-plugin` 只列 provider,**不列** `think.main` 的 binding。要直接看 binding:

```bash
uv run python -c "
from lca.harness.profile.resolve.resolve import resolve_profile
from lca.harness.composition.plan_compiler import compile_plan
plan = compile_plan(resolve_profile('profiles/web-standard.yaml'))
for n in plan.phase_graph.nodes:
    if n.id.startswith('think'):
        print(n.id, '->', n.binding)
"
```

**期望输出**:

```text
think.main -> phase.think.subgraph_host
```

如果这行还显示 `phase.think.standard` → patch 没生效,需要回到 `web-standard.yaml` 的
`phase.topology.standard.config.nodes` 部分检查。

## 4. 看整体服务状态

```bash
./scripts/lca-ops status
```

**期望输出(健康)**:

```text
● kernel_serve — running, healthy at http://127.0.0.1:8765/health
● infra — all services reachable
● lobehub — pid <pid>, :3010, healthy
● daemon — pid <pid>, connected
● onlyboxes — runtime ...
```

`status --json` 给 agent 用:

```bash
./scripts/lca-ops status --json
```

**JSON 结构**(stdout 是 list,每项是 step record):

```text
[{"level":"info","message":"Pipeline: status"},
 {"step":"stack.status"},
 {"service":"kernel_serve","status":"running","pid":..., "port":8765,
  "detail":"healthy at http://127.0.0.1:8765/health",
  "checks":[{"name":"health","ok":true,"detail":"http://127.0.0.1:8765/health"}]}]
```

`status` **不直接报告 profile 路径**(避免 health 端点泄漏 boot 信息);profile 由
`inspect-tree` / `why-plugin` 间接确认。

## 5. 看 boot 日志

### 5.1 Kernel stderr 文件

`KernelServeSpawner` 把每次 spawn 的 stderr 重定向到 `/tmp/lca-kernel.stderr.<pid>.<ts>.log`,**保留最近 5 份**(`spawner.py` `_STDERR_KEEP_N = 5`)。

```bash
ls -lt /tmp/lca-kernel.stderr.*.log | head -3
```

**典型 boot 头**(无 plugin enumeration;只有 lifecycle 事件):

```text
[debug] cognitive_run_driver_registered target=cognitive
[info]  event registry catalog populated entries=6
[info]  event pipeline registered pipeline=web-standard-event-pipeline version=1
... (运行期: runtime_lifecycle phase_started / phase_completed ...)
```

**boot 完成后 `anomaly_detector`** 会扫 spine 流,有 `phase.think.fold` EP 表示 think
phase 在跑(实际上 subgraph host 是 5 个 step,顶层 trace 看到的仍是 `phase.think.fold`)。

### 5.2 `/health` endpoint

```bash
curl -sS http://127.0.0.1:8765/health
```

**期望**:

```text
{"status":"ok",
 "runs":{"pending":0,"running":0,"waiting_input":0},
 "live":{"total_subscribers":0,"total_evicted":0,"journal_subscribers":0},
 "event_bus":{"published_total":0,"persisted_total":0,"delivered_total":0,"dropped_total":0,"fsync_policy":"batch","queue_depth":0},
 "plugin":{"registered":6,"expected":6,"missing":[],"registry_populated":true,"pipeline_registered":true,"cognitive_driver_registered":true},
 "devices":{"online":1,"devices":8}}
```

**关键判读**:
- `plugin.registered == expected == 6` + `missing=[]` = plugin 注册完整
- `cognitive_driver_registered=true` = cognitive 入口已装载
- `pipeline_registered=true` = event pipeline 已装载

> ⚠️ 注意:`/health` 不暴露 profile 路径(避免信息暴露)。要看 profile 用 `inspect-tree` / `why-plugin`。

## 6. 看运行时事实流(journal)

```bash
./scripts/lca-ops journal logs -v | tail -80
```

或离线回放一个 run:

```bash
./scripts/lca-ops journal logs -r <run_id>
```

**期望看到的事件**:任何 think.main visit 会触发:
- `phase.think.start` / `phase.think.fold` / `phase.think.end`(顶层)
- 内部 subgraph 5 步:不直接发 phase EP,但会发 `phase_graph.node.start/end` 每个 step
- `graph.subgraph_enter.v1` / `graph.subgraph_exit.v1`(`hook_seam` 装配,boot 时自动接 `session_log_emitter`)

## 7. 看 parity 测试(切前 vs 切后行为一致)

```bash
uv run pytest tests/cognition/test_think_subgraph_parity.py tests/harness/declarative/compile/test_bundle_subgraph_resolver.py tests/harness/graph/execute/test_interpreter_subgraph_hooks.py -q
```

**期望**:`32 passed`(切后)。Parity 断言:`host_result.payload == standard_result.payload == decision`,证明 decision payload 字节级一致。

## 8. 出问题快速定位

| 症状 | 看哪里 | 命令 |
|---|---|---|
| `kernel-restart` 失败 | stderr 文件 / spawn step | `./scripts/lca-ops kernel-restart`(返回非 0 时打 `actionable`) |
| `/health` 报 plugin missing | boot stderr | `ls -lt /tmp/lca-kernel.stderr.*.log` 看最近的 |
| run 行为变了 | journal | `./scripts/lca-ops explain <run_id>` |
| `inspect-tree` 没列 subgraph_host | profile 错了 | `git diff profiles/web-standard.yaml` |
| think.main binding 还是 standard | patch 没生效 | `uv run python -c "..."`(看 §3) |
| 其它 profile(coding-agent 等)走 standard | 它们没切 | 看 `profiles/<name>.yaml`,需要类似 patch |

## 9. 完整回滚

如果切后发现 parity 行为真出问题(目前不会):

```bash
git checkout profiles/web-standard.yaml tests/phase_executors.py lca/application/api/default_context.py
./scripts/lca-ops kernel-restart
```

回滚后 `web-standard.yaml` 的 `think.main` 恢复 `phase.think.standard`,走 monolithic brain。
`phase.think.subgraph_*` plugin 仍注册(无害,只是不调用)。