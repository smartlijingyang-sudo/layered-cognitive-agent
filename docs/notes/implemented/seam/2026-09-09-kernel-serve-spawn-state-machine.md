# Agent Note: KernelServe spawn 状态机化 + stderr 独立落盘

Status: implemented

> 配套 ADR:[`0213-kernel-serve-spawn-result-and-health-readiness.md`](../../adr/0213-kernel-serve-spawn-result-and-health-readiness.md)。
> 本 note 描述单点 seam 的改动;跨 ADR 影响走 ADR 本身。

## Problem

`lca/infrastructure/cli/services/kernel/serve.py::KernelServeService._spawn()`
把"启动 uvicorn 子进程 + 等 ready"压成 `bool` 返回,在 4 类失败场景下都
产生信息黑洞:

1. **preflight JWT 阻断**:`_spawn` 直接 `return False`,`heal()` 给操作员的
   detail 是"spawn failed; see /tmp/lca-kernel.log"——但 `heal` 自身不区分
   `block` / `OSError` / `timeout` 三种 `_spawn` 返回值来源。
2. **子进程瞬间被 SIGKILL**:`/tmp/lca-kernel.log` 只有一行 `Popen OK,pid=N`
   之后空白。`subprocess.Popen(stdout=log, stderr=log)` 在不同 Python 缓冲
   策略下不保证 stderr flush 进文件;agent 拿不到真 stderr。
3. **子进程启动但 plugin 注册失败**:`/health` 返回 200 + body `status="ok"`,
   但 `event registry catalog` 没 populated。当前 readiness 只看 HTTP 200,
   plugin 注册失败被静默放过(参见
   [`2026-09-04-event-bus-publisher-authorization.md`](../../implemented/seam/2026-09-04-event-bus-publisher-authorization.md)
   解决的是 publisher 授权失败返 5xx 的情况,**没解决 plugin 静默不注册**的情况)。
4. **并发 spawn 交错**:`/tmp/lca-kernel.log` 是单文件 append,两个 spawn 同时
   写会互相打断 stderr 行。

附加:

- `_spawn` 的 timeout 回退路径 `return pid_alive(proc.pid)` 让 30s 超时
  也被解释为 True,`heal()` 看到 True 就当 healthy,**操作员看到"重启退出
  0 但 kernel 实际没 ready"**。
- `lca-ops heal` 是"全站自愈"过载入口(infra / lobehub / daemon /
  onlyboxes / kernel_serve 都跑一遍),agent 想"只启 kernel"必须走完整
  pipeline,延迟大、行为不可预测。

## Proposal

### 1. `KernelServeSpawner` 单类取代 `_spawn() -> bool`

新文件 `lca/infrastructure/cli/services/kernel/spawner.py` 提供
`KernelServeSpawner` 类,把 spawn 拆成 5 个原子 step。每个 step 是结构化
`StepResult`(frozen Pydantic),最后聚合为不可变 `SpawnResult`(frozen
Pydantic,`extra="forbid"`,符合 ADR-0015 contracts-only 风格)。

5 个原子 step:

| step | 判定信号 | 失败 reason |
|---|---|---|
| `preflight` | JWT_SECRET 校验通过 | `jwt_preflight_blocked` |
| `start` | `subprocess.Popen` 成功 + PID 存在 | `popen_oserror` / `popen_no_pid` |
| `port_bound` | `port_listening(self.port)` 在 5 秒内 True | `port_not_bound` |
| `http_ready` | `GET /health` 30 秒内 200 + body `status="ok"` | `health_timeout` / `health_status_not_ok` / `health_unreachable` |
| `plugin_ready` | `/health` body `plugin.registered == expected` 且 `missing=[]` | `plugin_not_ready` |

### 2. stderr 每 spawn 一个独立文件

`Spawner.stderr_path = Path("/tmp/lca-kernel.stderr.<pid>.<yyyymmddhhmmss>.log")`
取代当前单文件 append。**自动保留最近 5 个文件**(超出按 mtime 删除),
不引入 lockfile。`stderr_path` 在 `SpawnResult` 暴露,agent 直接 `tail`。
这是对 `subprocess.Popen` 缓冲行为不可控的最小修复。

### 3. timeout 永不返回 True

`Spawner.run()` 只在 5 个 step 全部 `ok=True` 时返回 `SpawnResult(ok=True)`;
任一超时 → `SpawnResult(ok=False, failed_stage=<该 step>,
error="<timeout_seconds>s timeout", actionable=...)`。

`KernelServeService.heal()` 必须原样透传 `SpawnResult.actionable` 到
`ServiceState.next_action`,**不再 fallback 到"kernel 没在跑"**。

### 4. `kernel-restart` 子命令拆出 `stack.heal`

`cli/commands/kernel/restart.py` 的 `kernel-restart` 直接调
`KernelServeSpawner.run()` + 透传 `SpawnResult.actionable`。`stack.heal`
保留兜底(infra/lobehub/daemon 仍走它),但 `kernel_serve` 分支改为调
spawner 直接实例,**不再过载全站自愈**。

## Wire contract

`/health` 响应 schema 新增 `plugin` 字段(详见 ADR-0203 §4):

```json
{
  "status": "ok",
  "runs": {...},
  "live": {...},
  "event_bus": {...},
  "plugin": {
    "registered": 6,
    "expected": 6,
    "missing": [],
    "registry_populated": true,
    "pipeline_registered": true,
    "cognitive_driver_registered": true
  }
}
```

字段为**纯增量**;`status` / `runs` / `live` / `event_bus` 含义不变。lobehub
不解析新字段(ignore-safe),无 breaking change。

## Alternatives considered

### 把 `_spawn` 改成 dict 返回,不引入 Pydantic
不选。`SpawnResult` 必须可序列化(`SpawnResult.model_dump_json()` 给
`SpawnResult.actionable` 透传到 `ServiceState.next_action`)、字段固定
不可多写(`extra="forbid"`)、可静态回答 D1–D4 信息血统。普通 dict 不可
序列化为 JSON 时控制台输出不稳,且不能 freeze 阻止并行 spawn 互相覆盖字段。

### 把 stderr 同时打到 lca-ops 主 stderr
不选。`lca-ops kernel-restart` 在 background 跑时 agent 看不到主 stderr;
落盘文件是唯一可定位的物理证据。

### 自动保留最近 N 个 stderr 文件,用 lockfile 协调并发
不选。`subprocess.Popen` 已经把 stderr 接到独立文件描述符,文件按
`<pid>.<timestamp>` 自然不冲突,不需要 lockfile;反而 lockfile 引入新故障面
(NFS / stale lock / fchmod 失败)。

### 让 `spawn` 也支持 stop / status 探测职责
不选。ADR-0119 决定 4 明确 lca-ops 只 spawn + 探 `/health`,长管由 K6
负责。本 note 不扩张 service 边界。

## Acceptance criteria

- `lca/infrastructure/cli/services/kernel/spawner.py` 存在,5 个 step 全部
  有最小 unit test(`tests/infrastructure/cli/test_kernel_serve_spawner.py`,
  至少 5 step + 1 timeout + 1 stderr 文件保留 = 7 case)。
- `KernelServeService._spawn` / `_LOG_PATH` 在 PR 落地的同一 commit 删掉。
- `tests/infrastructure/cli/test_http_ready.py` 增加 `health_status_not_ok`
  与 `health_body_5xx` 两个 case,断言 `http_ready()` 在 body `status != "ok"`
  时返回 False。
- 现场失败 4 类(preflight 阻断 / 子进程瞬间死 / plugin 注册失败 / 并发
  spawn 交错)各自能被 `SpawnResult.failed_stage` + `actionable` 准确指示。
- `cli/commands/kernel/restart.py` 不再调 `stack.heal`,直接实例化
  `KernelServeSpawner`。
- `lca/infrastructure/cli/services/kernel/serve.py` 模块 docstring 第 17 行
  "spawn 路径经验"更新,新增"5 原子 step + SpawnResult"段。

## Risks

- Pydantic `SpawnResult.model_dump_json()` 在小内存环境下可能慢;spawn 是
  一次性操作(分钟级),不可接受的风险低。
- 自动保留最近 5 个 stderr 文件用 `os.stat().st_mtime` 排序,在 Linux 上
  行为稳定;macOS(开发机)mtime 与 ctime 表现不同,但本仓库 CI / 生产均
  Linux,不跨平台兼容,风险低。
- `/health` body 加 `plugin` 字段是 wire schema 增量,任何 cache / mock /
  文档生成 / lca-api SDK 同步都需要审一遍;通过 `tests/infrastructure/cli/test_kernel_health_body.py`
  + ADR 闭环 PR-2 守住。
- 现有 `lca.infrastructure.cli.services.kernel.serve` 模块被外部 import
  的只有 `KernelServeService` 类本身 + `_BIND_ALL_HOSTS` 常量;
  `grep -rn "from lca.infrastructure.cli.services.kernel.serve import"
  lca/ lca_kernel/ tests/` 必须 = 0 引用私有符号才能删 `_spawn`。

## Open questions

- 是否需要把 `KernelServeSpawner` 也通过 CLI 单测覆盖 preflight JWT warn
  vs block 的两条路径?(目前 `_preflight_jwt_secret` 返回 `"block" /
  "warn" / "ok"` 三态,但 `warn` 是否触发 spawn 阻塞?)
- 自动 stderr 文件轮转保留 N 个 vs 保留时间(24h)?倾向 N 5,简洁。
- 是否需要 `SpawnResult` 同时写到 `/var/log/lca-kernel.spawn.jsonl` 让
  supervisor 后续审计?目前不在范围内,留 follow-up。

## Related

- ADR [`0213`](../../adr/0213-kernel-serve-spawn-result-and-health-readiness.md)
- ADR [`0119`](../../adr/0119-webserver-as-plugin.md) 决定 4
- ADR [`0183`](../../adr/0183-event-bus-framework-ssot.md) / [`0181`](../../adr/0181-spine-as-events-publishers-subscribers.md)
- Implemented [`2026-09-08-kernel-serve-host-default-and-lan-probe.md`](../../implemented/seam/2026-09-08-kernel-serve-host-default-and-lan-probe.md)
- Implemented [`2026-09-04-event-bus-publisher-authorization.md`](../../implemented/seam/2026-09-04-event-bus-publisher-authorization.md)

## Migration plan

PR-1 落地 spawner + 委托重构 + 单元测试,spawner `SpawnResult(ok=True)`
路径实测 30 秒内 ready。PR-2 落地 `/health` plugin 字段 + 消费方同步。
PR-3 拆 `kernel-restart` 子命令 + 迁本 note 到 `implemented/seam/`。