# Agent Note: 子 note 2 — FileSink fd fsync 语义统一(L3 持久化协议)

Status: proposed

> 根 note 与元决策:[observation-convergence-root.md](2026-09-03-observation-convergence-root.md) / [ADR-0178](../../../adr/0178-observation-control-state-convergence.md)。本 note 收口根 note L4 未覆盖的 fd fsync 语义——**新 ADR 配套**(`docs/adr/0179-file-sink-fsync-protocol.md`,本 note PR 之一)。

## Problem

`lca/infrastructure/observability/spine/sinks/file_sink.py` 有 3 套 fd,各 fd 的 fsync 语义不同,**用户文档缺失**:

| fd | 文件 | 打开时机 | fsync 时机 | 失败语义 |
|---|---|---|---|---|
| `_fd` | `<run_id>.spine.jsonl` | `FileSink.__init__` `os.open(..., O_APPEND)` | 周期 batch(`_maybe_fsync`,100 条 / N ms)+ close 时 | 静默 log.error,继续 |
| `_exceptions_fd` | `<run_id>.exceptions.jsonl` | `FileSink.__init__` 同上 | **仅 close 时** | OSError 静默 |
| `TracingFileSink._fallback_fd` | `<run_id>.spine.jsonl` | fallback 路径 `_open_fallback_fd` | **无 fsync**(fallback 假设短暂) | 静默 |

具体证据(`file_sink.py`):

- `_maybe_fsync`(`file_sink.py:267`)触发条件:`_writes_since_fsync >= fsync_batch=100` **或** `monotonic - _last_fsync_at >= _fsync_interval`(默认未在 user-facing 文档化)
- `exceptions_fd` 仅在 `close()`(line 291)调用 `os.fsync(self._exceptions_fd)`,**运行期不 fsync**
- `TracingFileSink` 失败路径走 `os.write(self._fallback_fd, ...)`,fallback fd **无 fsync 策略**(commit `9f8aad75` 引入的 fence)

后果(用户 2026-09-03 反馈"traces/runs 下总有不全"):

- 进程崩溃 / OOM / SIGKILL 时,`_exceptions_fd` 可能丢 commit 后的 fd 内容
- `TracingFileSink` 走 fallback 时,fallback 文件可能比主 ledger 慢 N 条 event 才落盘,导致 fallback 路径上的 traceback 丢失
- 用户不知道 3 套 fd 3 套语义,debug 时无法判断"为什么这个 run 的 sidecar 没写"

DSH(`~/deepseek-harness`)的对照:`session-persistence-jsonl` 每次 append 都 `handle.sync()`(fsync),失败 `truncate(before)` 回滚。**LCA 的 batch fsync 是合理性能折中,但必须文档化 + 协议化**。

## Proposal

### 第一阶段 — 新 ADR:FileSink fsync 协议

`docs/adr/0179-file-sink-fsync-protocol.md` 定义:

```python
class FsyncProtocol(str, Enum):
    PER_WRITE = "per_write"     # 每次 write 后 fsync(DSH 形态,慢但正确)
    BATCH = "batch"             # N 条 / T ms batch fsync(LCA 现状,默认)
    COMMIT = "commit"           # 仅 close 时 fsync(最小开销,接受风险)
```

`FileSink.__init__` 接受 `fsync_protocol: FsyncProtocol = FsyncProtocol.BATCH` 参数,3 套 fd 走同一参数。`TracingFileSink.fallback_fd` 强制 `FsyncProtocol.PER_WRITE`(fallback 路径只用于异常路径,正确性优先)。

### 第二阶段 — 协议落地

`FileSink.__init__` 扩展:

- `_fd` / `_exceptions_fd` / `TracingFileSink._fallback_fd` 各自声明 fsync_protocol,存储在 `self._fsync_protocols: dict[int, FsyncProtocol]`
- `_maybe_fsync(fd)` 改为 `_maybe_fsync(fd, protocol)`,根据 protocol 决定阈值
- `close()` 按 protocol 决定是否 fsync(PER_WRITE 不再 close 时冗余;BATCH 在 close 时强制 fsync;COMMIT 仅在 close 时 fsync)

### 第三阶段 — 守门 + 文档化

- `FileSink` docstring 写明 3 套 fd 的 fsync 协议表
- `scripts/check_observation_ssot.py` 加规则:`TracingFileSink.fallback_fd 必须 PER_WRITE`
- `scripts/check_runtime_invariants.py`(note 5 新建)加规则:`FileSink.__init__ 必须声明 3 套 fd 的 fsync_protocol`

## Decision criteria

- `docs/adr/0179-file-sink-fsync-protocol.md` Accepted
- `FsyncProtocol` enum 上提 `lca/contracts/observability/ssot.py`(L1 SSOT 原则)
- `FileSink.__init__` 接受 `fsync_protocol` 参数
- 3 套 fd 都有明确 fsync 协议(不再是 3 套隐式行为)
- 用户文档 `docs/architecture/optimization-iterations.md` 或同级文档加一节"FileSink fd 持久化协议"

## Alternatives considered

### Why not 全部 PER_WRITE(DSH 形态)?

性能代价:`LLM streaming chunks` 高频 emit 路径每条 fsync → ~1000 IOPS 变 ~10 IOPS。LCA 当前 spine throughput ~2000 events/sec 降到 ~200 events/sec,**不可接受**。

### Why not 全部 BATCH(LCA 现状)?

`TracingFileSink.fallback_fd` 是异常路径——异常路径的语义是"宁可慢也别丢 traceback"。BATCH 在 SIGKILL 时丢 fallback fd 上最后 N 条 event = 丢 traceback = `exception.caught` payload < 4 KiB 不触发 offload = **永久丢证据**。这是 bug,不是性能折中。

### Why not 不写 ADR 直接改代码?

fsync 语义动 FileSink fd 生命周期,**跨 ADR-0169 L10(命名) + ADR-0065(账本)的范围**。按 README §1 必须先开 ADR。

### Why not 把 fsync 语义放 `FileSink` 内部而不抽 enum?

枚举是 L1 SSOT——`FsyncProtocol` 必须能被 `TracingFileSink`、`FileSink`、未来新 sink 共用。放 `FileSink` 内部 = `TracingFileSink` 反向 import,违反 AGENTS.md §3 C2(双平面分离)。

## Acceptance criteria

- `docs/adr/0179-file-sink-fsync-protocol.md` Accepted,引用 ADR-0178
- `FsyncProtocol` enum 在 `lca/contracts/observability/ssot.py`
- `FileSink.__init__` 接受 `fsync_protocol: FsyncProtocol` 参数
- `TracingFileSink._open_fallback_fd` 强制 `fsync_protocol=FsyncProtocol.PER_WRITE`
- 测试:`tests/observability/spine/test_file_sink_fsync.py` 覆盖 3 套 fd × 3 种 protocol = 9 case
- 文档:`docs/architecture/optimization-iterations.md` 或同级加"FileSink fd 持久化协议"节

## Risks

- **性能回归**:`PER_WRITE` 路径在 fallback 时降速 ~10x。如果 fallback 触发频率高(说明正常路径失败频率高),整体降速。需要监控:`scripts/check_runtime_invariants.py` 加规则"`TracingFileSink._open_fallback_fd` 触发次数 < 1/N event(N=100?)"
- **Windows fsync 语义差异**:DSH 用 `ensureDurableDirectoryWin32`(`session-persistence-jsonl/win32.ts`)处理。LCA 当前不显式区分平台,Windows 下 fsync 行为不同——需要在 ADR-0179 显式声明 POSIX-only(PER_WRITE) / Windows 用 `FlushFileBuffers`(COMMIT)。
- **测试覆盖率**:fsync 难以在 CI 单测里验证"真的 fsync 了"。需要 mock `os.fsync` 计数。

## Delete-when

- **兼容 fallback fd 默认 protocol**:若保留 `TracingFileSink.fallback_fd` 默认 BATCH(向后兼容),`# COMPAT(delete-when: 默认 PER_WRITE 已合 + 稳定 ≥ 14 天, tracking: ADR-0179-note-2)`
- **旧 `_maybe_fsync` 单参数签名**:若保留旧 API,`# COMPAT(delete-when: 全 caller 迁完, tracking: ADR-0179-note-2)`
- **新 `fsync_protocol` 参数缺省值**:若保留 BATCH 缺省(避免 caller 全改),`# COMPAT(delete-when: Profile / Bundle 全声明 + lint 命中 = 0, tracking: ADR-0179-note-2)`

## Related

- [observation-convergence-root.md](2026-09-03-observation-convergence-root.md) — 根 note
- [ADR-0178](../../../adr/0178-observation-control-state-convergence.md) — 元决策
- `lca/infrastructure/observability/spine/sinks/file_sink.py` — FileSink 当前实现
- `lca/infrastructure/observability/spine/sinks/tracing_file_sink.py` — TracingFileSink 当前实现
- `~/deepseek-harness/packages/session/session-persistence-jsonl/src/index.ts` — DSH fsync 参考
- `~/deepseek-harness/packages/util/atomic-write/src/index.ts` — DSH atomic-write(非 fsync,跨进程 lock)参考
