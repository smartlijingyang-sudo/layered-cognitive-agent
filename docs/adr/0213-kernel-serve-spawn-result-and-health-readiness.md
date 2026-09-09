# ADR-0213: KernelServe spawn 结果结构化 + /health plugin readiness 字段

**状态:** Implemented (PR-1 + PR-2 + PR-3, 2026-09-09)
**日期:** 2026-09-09
**父 ADR:** [0119-webserver-as-plugin.md](0119-webserver-as-plugin.md) ·
[0119-followup-gateway-name-removal.md](0119-followup-gateway-name-removal.md)
**关联 ADR:** [0183-event-bus-framework-ssot.md](0183-event-bus-framework-ssot.md) ·
[0181-spine-as-events-publishers-subscribers.md](0181-spine-as-events-publishers-subscribers.md) ·
[0117-process-lifecycle-env-whitelist.md](0117-process-lifecycle-env-whitelist.md) ·
[0090-observability-health-ssot.md](0090-observability-health-ssot.md)(如存在)
**关联 Note:**
[`docs/notes/implemented/seam/2026-09-08-kernel-serve-host-default-and-lan-probe.md`](../notes/implemented/seam/2026-09-08-kernel-serve-host-default-and-lan-probe.md)
[`docs/notes/proposed/seam/2026-09-09-kernel-serve-spawn-state-machine.md`](../notes/proposed/seam/2026-09-09-kernel-serve-spawn-state-machine.md)

## 背景

`lca/infrastructure/cli/services/kernel/serve.py` 的 `_spawn()` 把"启动一个
uvicorn 子进程 + 等 ready"压缩成 `bool` 返回。该函数在 4 类失败场景下
都会产生**信息黑洞**,操作员和 agent 拿到不到根因:

| 失败场景 | 现象 | 根因 |
|---|---|---|
| preflight JWT 阻断 | `heal()` 返回 STOPPED,detail="spawn failed; see /tmp/lca-kernel.log" | `_spawn` 直接 `return False`,**不携带原因**(block / OSError / timeout 三种混在一起) |
| 子进程瞬间被 SIGKILL | `/tmp/lca-kernel.log` 只有一行 `Popen OK,pid=N` 之后空白,`state()` 一会儿后变 STOPPED | `subprocess.Popen(stdout=log, stderr=log, buffering=0)` 在不同 Python 缓冲策略下不保证把 stderr flush 进文件;外加 spawn timeout 走 `return pid_alive(proc.pid)` 让 timeout 误报 True |
| 子进程启动但 plugin 注册失败 | HTTP 200 但 body `status=ok` 字段缺失或 plugin 注册计数=0 | `_spawn` 不校验 plugin 注册,只看 `/health` 返回 200;`/health` 200 ≠ 业务可服务 |
| 并发 spawn 交错 | `/tmp/lca-kernel.log` append 模式被两个 spawn 同时写 | 进程 A 的 stderr 行被进程 B 的 stderr 打断 |

此外 `lca-ops heal` 是"全站自愈"过载入口(infra / lobehub / daemon / onlyboxes / kernel_serve 都跑一遍),agent 想"只启 kernel"要走完全部判断,延迟大、行为不可预测。

`/health` 当前响应 schema 缺失 plugin readiness 信号(ADR-0181 / 0183 已
约束 journal 事件 catalog 与 publisher 授权,但 `/health` body 没有
`event registry populated / pipeline registered / cognitive driver
registered` 的 SSOT)。

**触发条件:**
1. 2026-09-09 现场:`./scripts/lca-ops kernel-restart` 4 次尝试中 3 次失败,
   失败信息统一 fallback 到 `lca_kernel serve 没在跑。heal 会自动拉起。`,
   agent 拿到"出错信息"无法区分 preflight 阻断 / 子进程瞬间死 / plugin
   注册失败 / 超时。
2. `heal()` 全站自愈设计无法做 kernel-only 诊断。
3. ADR-0119 决定 4 把 LCA 进程入口切到 `uv run python -m lca_kernel serve`,
   `lca-ops` 只负责 spawn + `/health` 探活,但 spawn 这层的事后取证留白。

## 决定

### 1. `KernelServeSpawner` 单类取代 `_spawn() -> bool`

新文件 `lca/infrastructure/cli/services/kernel/spawner.py` 提供
`KernelServeSpawner` 类,**单职责**:把 spawn 拆成 5 个原子 step,每个 step
返回结构化 `StepResult`,最后聚合为不可变 `SpawnResult` dataclass
(`frozen=True`, `extra="forbid"`,符合 ADR-0015 contracts-only 风格)。

5 个原子 step:

| step | 判定信号 | 失败信号 |
|---|---|---|
| `preflight` | `JWT_SECRET` / `LCA_JWT_SECRET` 校验通过 | `reason="jwt_preflight_blocked"`,`message=...` |
| `start` | `subprocess.Popen` 成功且 PID 存在 | `reason="popen_oserror"`,`errno`, `strerror` |
| `port_bound` | `port_listening(self.port)` 5 秒内 True | `reason="port_not_bound"`,`pid`, `port` |
| `http_ready` | `GET /health` 30 秒内 200 且 body `status="ok"` | `reason="health_timeout"` / `health_status_not_ok` / `health_unreachable` |
| `plugin_ready` | `/health` body `plugin.registered == plugin.expected` 且 `missing=[]` | `reason="plugin_not_ready"`,`registered`,`expected`,`missing` |

每个 `StepResult` 字段:

```python
class StepResult(BaseModel):
    stage: Literal["preflight", "start", "port_bound", "http_ready", "plugin_ready"]
    ok: bool
    duration_ms: int
    error: str | None = None        # 失败原因短描述
    detail: dict[str, Any] = {}     # 阶段特异调试信息(attempts / last_status / last_body / pid / port)
```

`SpawnResult` 是 `StepResult` 的聚合:

```python
class SpawnResult(BaseModel):
    ok: bool                                  # 5 个 step 全 ok 才 True
    failed_stage: str | None = None           # 哪个 step 失败
    steps: list[StepResult]                   # 5 个 step 的完整序列
    pid: int | None = None
    port: int
    stderr_path: Path                          # 落盘的 stderr 文件
    duration_ms: int
    actionable: str | None = None             # 给操作员/agent 的下一步建议
```

### 2. stderr 每 spawn 一个独立文件

`Spawner.stderr_path = Path("/tmp/lca-kernel.stderr.<pid>.<yyyymmddhhmmss>.log")`
取代当前 `/tmp/lca-kernel.log` 单文件 append。**自动保留最近 5 个文件**(超出按
mtime 删除),不引入新的 lockfile / inode-state,避免 lca-ops 自身 daemon 化
时的副作用。`stderr_path` 出现在 `SpawnResult` 里,agent 直接 `tail`。

### 3. timeout 永不返回 True

`_spawn` 当前 `return pid_alive(proc.pid)` 让 30s 超时也可能被解释为成功
(因为 `heal()` 看到 True 就当 healthy)。新 `Spawner.run()` 只在 5 个 step
全部 `ok=True` 时返回 `SpawnResult(ok=True)`;任一超时 → `SpawnResult(ok=False,
failed_stage=<该 step>, error="<timeout_seconds>s timeout", actionable=...)`。

`heal()` 与 `restart()` 必须**原样透传** `SpawnResult.actionable` 到
`ServiceState.next_action`,**不再 fallback 到"kernel 没在跑,去 heal"**。
本决定同步把 `kernel-restart` 子命令拆出 stack.heal:
新增 `cli/commands/kernel/restart.py` 的 `kernel-restart` 直接调
`Spawner.run()` + 透传 actionable,**不再调 `stack.heal` 走全站自愈**。
`stack.heal` 保留为兜底(infra/lobehub/daemon 仍走它)。

### 4. `/health` 响应 schema 新增 `plugin` 字段

`lca_kernel/server/health.py`(新增或修改)按以下 schema 返回:

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

字段 SSOT:

| 字段 | 来源 | 写入点 |
|---|---|---|
| `registered` | `event registry catalog populated entries=N` 日志对应的 registry snapshot | `lca_kernel/events/registry.py::EventRegistry.size()` |
| `expected` | active profile + bundles 的 plugin 总数 | `lca_kernel/profile/runtime.py::count_expected_plugins()` |
| `missing` | `expected - registered` 的差集 | 由前两项计算 |
| `registry_populated` | 当前 boot lifecycle 是否过 FIBER_SPAWN | `lca_kernel/boot.py::BootLifecycleMarker.registry_populated` |
| `pipeline_registered` | event pipeline registered 日志 | 同上 |
| `cognitive_driver_registered` | cognitive_run_driver_registered 日志 | 同上 |

`/health` body 字段扩展是 wire schema 变更,**消费者必须同 PR 闭环**:

| 消费者 | 必改 |
|---|---|
| `lca/infrastructure/cli/service/service.py::http_ready` | 校验 `body["status"] == "ok"`(目前只校验 HTTP 200,允许 200 配 body 错误) |
| `lca_kernel/transport/webserver/handlers/health/*.py`(如有) | 直通新字段 |
| `lobehub-ui/src/**/lca-api*` | 不解析新字段,前端 ignore-safe;无需改 |
| `tests/infrastructure/cli/test_kernel_serve_*` | 新增 `body status="ok"` 校验测试 |
| `tests/infrastructure/cli/test_http_ready.py`(已有,ADR-0183-followup) | 扩 `health_body_not_ok` case |

### 5. `KernelServeService` 拆分

`lca/infrastructure/cli/services/kernel/serve.py` 保留 service 形态
(`state()` / `heal()` / `restart()` 三入口不动),但 `_spawn()` / `_LOG_PATH`
/ `pid_alive` 包装 / `_probe_proxy_lan` 全部委托给 `KernelServeSpawner`:

```python
class KernelServeService:
    def __init__(self, config, root):
        self._config = config
        self._root = root
        self._spawner = KernelServeSpawner(config=config, root=root)

    def heal(self) -> ServiceState:
        current = self.state()
        if current.is_running:
            return current
        result = self._spawner.run()
        if not result.ok:
            return ServiceState(
                status=ServiceStatus.STOPPED,
                detail=f"spawn failed at stage={result.failed_stage}: {result.error}",
                why=f"`lca_kernel serve` stage={result.failed_stage} error={result.error}",
                next_action=result.actionable or "./scripts/lca-ops logs",
            )
        return self.state()
```

`_BIND_ALL_HOSTS` 与 `_probe_proxy_lan` 逻辑保留(被 `http_ready` step 复用
LAN 探活);不新造 PARALLEL probe 入口。

### 6. 不在范围(scope creep 防护)

| 项 | 原因 |
|---|---|
| `/health` 字段由 kernel 主动 push 到 lobehub cache | 当前架构 lobehub 走 GET 即时探活,push 是反向耦合 |
| `event registry catalog populated entries=N` 日志格式变更 | 已有 ADR-0116 / 0181 约束,本 ADR 只读不写 |
| spawner 拆成 daemon / supervisor | ADR-0119 决定 4 明确 K6 长管 LCA 进程,lca-ops 只 spawn 不 supervise |
| capability key / env / module 改名 | 已在 [0119-followup-gateway-name-removal.md](0119-followup-gateway-name-removal.md) 闭环,本 ADR 不并行 |
| `tests/cognition/test_*` / `tests/integration/*` 全量重跑 | 跟随 pre-push-checks skill 即可 |

### 7. wire schema 兼容期

`/health` 新字段为**纯增量**(`status` / `runs` / `live` / `event_bus` 保持原值与含义),lobehub / 老 agent 不解析新字段,无 breaking change。**不引入** dual-key shim,只追加。

## 验证矩阵

| 项 | 命令 |
|---|---|
| Pre-push checks | 调 [`.agents/skills/lca-pre-push-checks/SKILL.md`](../../.agents/skills/lca-pre-push-checks/SKILL.md) 选最小命令集 |
| ruff + format | `ruff check lca/infrastructure/cli/services/kernel/ lca_kernel/server/ tests/infrastructure/cli/` |
| pytest spawn | `uv run pytest tests/infrastructure/cli/test_kernel_serve_spawner.py -v` |
| pytest http_ready | `uv run pytest tests/infrastructure/cli/test_http_ready.py -v` |
| pytest health body | `uv run pytest tests/infrastructure/cli/test_kernel_health_body.py -v`(新增) |
| 端到端 spawn | `./scripts/lca-ops kernel-restart`(新子命令) → `./scripts/lca-ops status --json` kernel_serve running on `:8765`,plugin 注册字段非空 |
| 端到端 failure | 临时改 profile 故意引入 plugin id miss → `./scripts/lca-ops kernel-restart` 退出码非 0,`SpawnResult.actionable` 指向具体 registry catalog populate 失败 |
| ARCHITECTURE checks | `bash scripts/lint-imports.sh`(lca_kernel/server/ 不反向依赖 contracts 之外) |
| journal regression | `uv run pytest tests/test_health_event_bus_field.py` 通过(若有) |

## 落地 PR 拆解

- **PR-1**: ADR-0203 + `KernelServeSpawner` 实现 + `KernelServeService` 委托重构 + `tests/infrastructure/cli/test_kernel_serve_spawner.py`(5 个 step 各 1 case + timeout + stderr 文件保留)
- **PR-2**: `/health` body 加 `plugin` 字段 + `http_ready` body 校验 + `tests/infrastructure/cli/test_kernel_health_body.py` + 消费方 (`webserver handlers / tests`) 同步
- **PR-3**: `kernel-restart` 子命令拆出 + `stack.heal` 保留兜底 + `docs/notes/implemented/seam/2026-09-09-kernel-serve-spawn-state-machine.md` 落地(由 proposed 移过来)

## 删除条件

- `KernelServeService._spawn` 与 `_LOG_PATH` 整个删掉。
- `_probe_proxy_lan` 公开方法如果不再被外部调用,inline 进 `http_ready` step。
- `stack.heal` 里 `kernel_serve` 分支改调用 `KernelServeSpawner` 直接实例。
- `tests/infrastructure/cli/test_kernel_serve_probe_lan.py`(旧 LAN probe 单测)保留,只是覆盖路径合并到 spawner 测试。
- ADR-0119-followup-2 名字清理不在本 ADR 范围,不联动。