# ADR-0118: Kernel HMR — Live Patches for `cordis.patch.yml`

> **状态：** Accepted
> **日期：** 2026-08-31
> **配套 ADR：** [ADR-0115](./0115-kernel-transport-boundary.md) K8（hot-reload 职责单独立项）· [ADR-0085](./0085-plugin-everything-explained.md) 插件哲学 · [ADR-0109](./0109-plugin-metadata-mandate-and-budgetaware-removal.md) 元数据 + 废弃 · [ADR-0062](./0062-plugin-runtime-cleanup.md) 插件运行时收口 · [ADR-0071](./0071-composer-per-cluster.md) composer per cluster
>
> **落地：** `lca_kernel/hmr.py` —— `PatchConfig` / `PatchWatcher` / `validate_patch` / `ReloadError`，由 `tests/lca_kernel/test_hmr.py` 守

## 背景

[ADR-0115](./0115-kernel-transport-boundary.md) 决定 1 在 K1–K8 八个职责里写了「K8: cordis.patch.yml watcher + 热重载」，但 PR-2 实施只到 K7。本 ADR 单独承接 K8，把 HMR 范围、协议和验收标准锁下来。

deepseek-harness 的 `app-boot` 在 `host/hmr` 包里提供两个原语：

```typescript
// packages/host/hmr/src/watcher.ts
export class PatchWatcher {
  constructor(private readonly config: PatchConfig, private readonly onChange: (event: PatchEvent) => void) {}
  start(): void   // debounce + listen for fs change
  stop(): void
  reload(): Promise<void>   // 显式 reload
}

// packages/host/hmr/src/index.ts
export function watchUserPatches(binName: string, dir = process.cwd()): PatchWatcher {
  // 默认监听 <dir>/cordis.patch.yml
}
```

LCA 当前没有 HMR：plugin / profile 改动需要重启进程。deepseek 的实现是**进程内 hot-swap**，依赖 cordis Fiber 的 dispose + restart。

LCA 的 cordis 实例运行在 Starlette lifespan 内，**进程内 hot-swap 风险**：Brain / Body / Agent runtime 的 in-flight 状态会被清掉，会话级 cache、journal 写入、Run 会话全部要重启。**本期决定用更保守的「file watcher + reload signal」模型：watcher 只观察文件变更，把 reload 决策交给上层 supervisor（uvicorn --reload / k8s rollout / lca-ops restart）。**

## 决定

### 决定 1：K8 = 「文件监听 + reload 信号」，不做进程内 hot-swap

LCA kernel 不在自身进程内 dispose / re-spawn cordis Fiber；这违反 ADR-0062 的「运行期不私自改 State」。K8 的职责是：

1. 监听 `<dir>/cordis.patch.yml`（默认 `Path.cwd()`，可由 `PatchConfig.path` 覆盖）。
2. 文件 mtime 变化时调用 `validate_patch(patch)`；通过则 `emit PatchEvent`，未通过则 `raise ReloadError`。
3. 上层（uvicorn `--reload` / k8s readiness probe / `lca-ops kernel restart`）收到事件后自行决定 reload 方式。

进程内 hot-swap 留作后续 ADR（需要解决 in-flight Run 会话挂起 / journal sealed 边界 / checkpoint reload 等问题，复杂度远超本期）。

### 决定 2：`PatchConfig` 数据类 + 三个常量

```python
@dataclass(frozen=True, slots=True)
class PatchConfig:
    path: Path                       # 默认 Path("cordis.patch.yml")
    debounce_ms: int = 250           # 250ms 静默期合并连续修改
    poll_interval_ms: int = 1000     # fs watcher poll 间隔
    allow_empty: bool = False        # 空 patch 文件是否允许
```

三个常量：
- `DEFAULT_PATCH_PATH = Path("cordis.patch.yml")`
- `PATCH_EVENT_KIND = "kernel.hmr.patch"`  —— 上层订阅这个 kind 决定 reload
- `MIN_DEBOUNCE_MS = 50` —— 防抖下限（避免 fs 高频事件耗 CPU）

### 决定 3：`PatchWatcher` Protocol + `PollingPatchWatcher` 默认实现

```python
class PatchEvent:
    ts: float
    path: Path
    raw: Mapping[str, object]   # 已解析的 patch 字典
    patch_kind: str              # "user" / "bundle" / "overlay"

class PatchWatcher(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def reload_now(self) -> PatchEvent: ...   # 同步触发一次

class PollingPatchWatcher:
    """默认实现:daemon thread + poll mtime + debounce。

    Why polling over inotify:
    - 跨平台(macOS / Linux / WSL)行为一致
    - 不依赖 watchdog / pyinotify 等 native 扩展
    - poll_interval 1s 对 hot-reload 场景足够(K8s readiness 也是秒级)
    """
```

### 决定 4：`validate_patch` + `ReloadError`

`validate_patch(patch: Mapping) -> None`：
- 必须是 mapping
- 必须含 `version: str` 字段
- 顶层 keys 仅允许 `version` / `bundles` / `profiles` / `patches` / `settings`
- 不递归校验子结构（patch 内容由 resolve 阶段校验；HMR 只做 shape gate）

`ReloadError(KernelError)`：
- `path: Path` 字段
- `reason: Literal["missing", "shape", "empty", "io"]` 字段
- 触发条件：文件不存在（allow_missing=False）/ 解析失败 / 顶层结构非法 / patch 为空

### 决定 5：`cordis.patch.yml` 是**叠加**而非**替换**

deepseek 的 `app-boot/composeEntries` 把 patch 当作多层 overlay 的最高层：bundle → profile → home → patch → env。LCA K8 不做 compose（避免重做 resolve 的职责），只在 HMR 路径上：

- 提供 `summarize_patch(raw) -> str` 给 `lca-ops` 打印 patch 内容
- 提供 `summarize_pending_reload(ctx) -> bool` 给 transport 健康检查（pending = True 时返回 503 触发 k8s 重启）

## 验收

| # | 项 | 验证命令 |
|---|---|---|
| A1 | `lca_kernel.hmr.PatchConfig` 不可变 + 默认值正确 | `pytest tests/lca_kernel/test_hmr.py` |
| A2 | `validate_patch` 接受 4 种合法顶层 keys | 同上 |
| A3 | `validate_patch` 拒绝非法 keys / 非 mapping / 缺失 `version` | 同上 |
| A4 | `reload_now()` 在文件不存在时 raise `ReloadError(reason="missing")` | 同上 |
| A5 | `reload_now()` 在空文件 + allow_empty=False 时 raise `ReloadError(reason="empty")` | 同上 |
| A6 | `PollingPatchWatcher.start()/stop()` 不泄漏线程（`stop()` 后 daemon 退出） | 同上 |
| A7 | 写入 patch 文件后 watcher 在 `debounce_ms + poll_interval_ms` 内触发 callback | 同上 |
| A8 | `lca_kernel` 0 新 transport 知识（边界测试 12 项全 pass） | `pytest tests/lca_kernel/test_boundary.py` |
| A9 | `importlinter kernel-domain-isolation` 配置可用（不能用「子包」forbidden） | `lint-imports` |

## 不做什么

- **不做** 进程内 Fiber dispose + re-spawn（违反 ADR-0062）
- **不做** patch 内容深度校验（交给 resolve 阶段）
- **不做** 多文件监听（只监听 `cordis.patch.yml`）
- **不做** WebSocket 推送（交给 transport layer）
- **不做** watchfiles / watchdog 依赖（polling 已足够）

## 后续 ADR

- ADR-0119 暂未立项。`/runs/{id}/doctor` 的 HMR 状态端点可在该 ADR 内与运行诊断合并。
