# ADR-0117: Process 生命周期 + Fail-loud + 环境变量白名单

> **状态：** Accepted
> **日期：** 2026-08-31
> **落地证据：**
> - **K6** `lca_kernel/lifecycle.py`:`ShutdownCoordinator` Protocol + `DefaultShutdownCoordinator` 实现(LIFO dispose, is_shutting_down 去重);`install_fail_loud` 装 sys.excepthook + asyncio handler + threading.excepthook;`install_signal_handlers` 装 SIGTERM(0) / SIGINT(130);`FAIL_LOUD_RELEASE_TIMEOUT_MS = 2000`(deepseek 借鉴)
> - **K7** `lca/infrastructure/env/bootstrap.py`:`BOOTSTRAP_NAMES`(46 个:Python/venv / shell/locale / VCS / 网络信任)+ `BOOTSTRAP_PREFIXES`(13 个,LCA_/LLM_/GATEWAY_/...)+ `BOOTSTRAP_FORBIDDEN`(LCA_PROFILE / LCA_KERNEL_KEY / LCA_INTERNAL_INJECTION)
> - **K7** `lca/infrastructure/env/layered.py`:`filter_env_keys` 三层模型(ambient / .env / profile refs)
> - **K7** `lca_kernel/env.py`:kernel facade `load_layered_env(bin_name, dir, allow_unknown=False)` + `EnvSnapshot`(ambient + filtered dotenv + allowed/blocked keys)
> - **D5** `LCA_PROFILE` 通过 argv 而非 .env 决策(由 `BOOTSTRAP_FORBIDDEN` 强制)
> - **K8** 见 [ADR-0118](./0118-kernel-hmr-patch-watcher.md)
> **配套 ADR：** [ADR-0115](./0115-kernel-transport-boundary.md) Kernel/Transport 边界 · K6 + K7 专项落地
>
> **范围**:本 ADR 是 [ADR-0115](./0115-kernel-transport-boundary.md) 决定 1 中 **K6**(Process 生命周期 + Fail-loud)与 **K7**(环境变量加载 + 白名单)的具体落地。K8 HMR 单独在 [ADR-0118](./0118-cordis-patch-hmr.md) 中立项。

## 背景

deepseek-harness 的 `packages/boot/app-boot/src/index.ts` 提供了三个当前 LCA 完全缺失的 kernel 能力:

### K6 缺失:`installFailLoud` + `createProcessShutdown`

```typescript
// deepseek app-boot
function installFailLoud(binName: string, process: NodeJS.Process,
                         dispose: () => Promise<void>): void {
  // 装 unhandledRejection + uncaughtException handler
  // 任何 plugin setup 抛的异常都不会让进程静默死亡
  // 而是:log → dispose → exit code 1
}

function createProcessShutdown(dispose: () => Promise<void>): ProcessShutdown {
  // 装 SIGTERM / SIGINT handler
  // SIGTERM = supervisor 正常 stop → exit 0
  // SIGINT = user interrupt → exit 130
}
```

`apps/cli/src/profile-boot.ts:220-235` 在每次 `runProfile` 都调用:

```typescript
process.on('SIGTERM', () => { interrupt(0) })    // supervisor 正常 stop
process.on('SIGINT', () => { interrupt(130) })    // user Ctrl-C
installFailLoud(NAME, process, async () => {
  await app.current?.fiber.dispose()              // boot 期也兜底
})
```

**LCA 现状**:
- 没有 `installFailLoud`:任何 plugin setup 抛异常 → uvicorn 默认行为 → 错误码退出或更糟(静默)
- 没有 SIGTERM/SIGINT handler:uvicorn/granian 自己装,但 boot 期(从 `compile_profile` 开始到 uvicorn listen 之间)的信号没人管
- 没有 process-level shutdown 协调:kernel 已 dispose 但 transport 还在 serve 时,信号到达会有竞态

### K7 缺失:`loadLayeredEnv` + `BOOTSTRAP_NAMES` 白名单

```typescript
// deepseek app-boot
const BOOTSTRAP_NAMES = new Set([
  // Process launch & module resolution (always allow)
  'PATH', 'HOME', 'USERPROFILE', 'SHELL',
  'NODE_OPTIONS', 'NODE_PATH', 'NODE_EXTRA_CA_CERTS',
  'LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT',
  // Interpreter startup hooks
  'BASH_ENV', 'ENV', 'SHELLOPTS', 'BASHOPTS',
  'PERL5OPT', 'PERL5LIB', 'PYTHONSTARTUP', 'PYTHONPATH',
  'RUBYOPT', 'RUBYLIB', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS',
  'JDK_JAVA_OPTIONS', 'PYTHONHOME',
  // VCS hooks & redirects
  'GIT_SSH', 'GIT_SSH_COMMAND', 'GIT_EXTERNAL_DIFF', 'GIT_PAGER',
  'GIT_EDITOR', 'GIT_ASKPASS', 'SSH_ASKPASS',
  'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM', 'GIT_CONFIG_COUNT',
  'EDITOR', 'VISUAL', 'PAGER',
  // Network reach & trust
  'DEEPSEEK_BASE_URL', 'DEEPSEEK_SEARCH_BASE_URL',
  'SSL_CERT_FILE', 'SSL_CERT_DIR',
  'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
  'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE',
  'NODE_TLS_REJECT_UNAUTHORIZED',
])
const BOOTSTRAP_PREFIXES = ['DSH_', 'XDG_', 'DYLD_', 'BASH_FUNC_']

function loadLayeredEnv(binName, dir = process.cwd()): { [k: string]: string } {
  // 读 .env 但只覆盖 BOOTSTRAP_NAMES ∪ (任何 *_PREFIXES) ∩ (env 内存在的)
  // 关键:.env 不能 SET 任何 BOOTSTRAP_NAMES 之外的环境变量
  //      .env 不能 OVERRIDE ambient env 中不存在的 key(防止意外注入)
  //      这两个规则确保 .env 只能"补全"既有行为,不能"新增"或"破坏"系统
}
```

**LCA 现状**:
- `lca/infrastructure/env/` 目录**不存在**
- `.env` 加载大概率是 `python-dotenv` 默认行为(load all,override all),潜在风险:
  - `.env` 误覆盖 `PATH` / `PYTHONPATH` 等关键变量
  - `.env` 注入系统环境不存在的 key(如随机生成的恶意变量)
  - 缺白名单 = 缺可审计性,无法知道 `.env` 实际影响了什么

### 借鉴边界

K6 + K7 在 deepseek 是 `app-boot` 包的子函数;在 LCA 本 ADR 拆为两个独立模块:
- `lca-kernel/lifecycle.py`(K6)
- `lca-kernel/env.py`(K7)
- `lca/infrastructure/env/{bootstrap,layered}.py`(K7 的基础设施层)

保持 K6 / K7 各自一个文件,**不混**(评审一致反对 `_install_observability` 双源同名不同职的反模式)。

## 决定

### 决定 1:K6 = `lca-kernel/lifecycle.py`

```python
# lca-kernel/lifecycle.py
"""Process lifecycle: signal handlers + fail-loud兜底。

Public API
----------
- :func:`install_fail_loud`   — 装 unhandledRejection / uncaughtException handler
- :func:`install_signal_handlers` — 装 SIGTERM / SIGINT handler
- :func:`create_shutdown_coordinator` — 返回 ShutdownCoordinator(协调 kernel + transport dispose)

Why a dedicated module
----------------------
Process exit 是不可逆的最后机会;LCA 之前没有 fail-loud,plugin setup
抛异常会让进程在 uvicorn 没 listen 时静默死亡。Signal handler 跟
plugin tree 生命周期要严格分离,handler 只调 ShutdownCoordinator,
由 Coordinator 决定真正的 dispose 顺序(transport 先关 listen,
再 dispose kernel,最后 process exit)。
"""

import signal
from contextlib import suppress
from typing import Callable, Protocol

class ShutdownCoordinator(Protocol):
    """协调 process 退出时的多源 dispose 顺序。

    Sources of shutdown:
    1. SIGTERM (supervisor): exit 0
    2. SIGINT (user Ctrl-C): exit 130
    3. unhandledRejection / uncaughtException (bug): exit 1
    4. ctx.appExit() (one-shot runner): exit 0
    """
    async def shutdown(self, code: int) -> None: ...
    def interrupt(self, code: int) -> None: ...
```

**借鉴 deepseek `installFailLoud` + `createProcessShutdown` 完整语义,但加上**:
- ShutdownCoordinator 单一所有权(避免 LCA 当前 `_dispose_context` 在 boot.py + lifespan.py + gateway/app.py 三处重复)
- Signal handler 装的时候记录 `original_handlers`,dispose 时还原(否则 tests 会受影响)

### 决定 2:K6 fail-loud 触发条件

```python
import asyncio
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

# deepseek app-boot 同款常量:release 阶段 dispose 必须在 2s 内完成,
# 否则 process 强退;terminal restore 不能让 Node 因 event loop 空了退出 0
FAIL_LOUD_RELEASE_TIMEOUT_MS: int = 2000

def install_fail_loud(coordinator: ShutdownCoordinator) -> None:
    """Fail loud on any unhandled rejection or uncaught exception.

    范围:
        - asyncio.Task 异常未 await(主事件循环)
        - 子线程未捕获异常(threading.excepthook,Python 3.8+)
        - ThreadPoolExecutor / ProcessPoolExecutor worker 异常
        - signal handler 未装 (boot 期间)

    不范围(交给 transport / uvicorn):
        - uvicorn 已 listen 后的 HTTP 请求异常(transport 自己 catch)
        - keyboard interrupt(已被 SIGINT handler 接走)
    """
    def on_unhandled(exc_type, exc_value, exc_tb):
        if coordinator.is_shutting_down():
            return  # 已 dispose,避免双重 exit
        logger.error("unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        coordinator.shutdown(1)  # async,fire-and-forget

    # 1. 主线程 sys.excepthook
    sys.excepthook = on_unhandled

    # 2. asyncio loop 异常(用 get_running_loop,因为 install_fail_loud 在 async 上下文调用)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # install_fail_loud 在 boot 启动前(无 running loop)调用,延后到 loop 创建
        def _install_when_running() -> None:
            try:
                asyncio.get_running_loop().set_exception_handler(
                    lambda loop, ctx: on_unhandled(
                        ctx.get('exception_type', Exception),
                        ctx.get('exception'),
                        None,
                    )
                )
            except RuntimeError:
                pass  # 没 loop 也不挂,继续
        asyncio.events._set_running_loop = _install_when_running  # type: ignore
    else:
        loop.set_exception_handler(lambda loop, ctx: on_unhandled(
            ctx.get('exception_type', Exception),
            ctx.get('exception'),
            None,
        ))

    # 3. 子线程(threading.excepthook,Python 3.8+)
    def on_thread_exception(args: threading.ExceptHookArgs) -> None:
        on_unhandled(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = on_thread_exception

    # 4. ThreadPoolExecutor / ProcessPoolExecutor worker 异常
    #     (通过自定义 Executor subclass 包装 submit,捕获 future.exception())
    #     注:标准库无全局 hook,需要在 spawn worker 的代码里用自定义 Executor
```

**关键**:
- `is_shutting_down()` 防双重 dispose(被 signal 和 unhandled 双重触发时只 dispose 一次)
- `asyncio.get_running_loop()` 替代 deprecated `asyncio.get_event_loop()`(Python 3.12+ 强制)
- `threading.excepthook` 处理子线程(常见 bug 源:子线程 spawn 后抛异常静默死亡)
- `FAIL_LOUD_RELEASE_TIMEOUT_MS = 2000` 借鉴 deepseek `app-boot/src/index.ts` 同一常量

### 决定 3:K7 = `lca-kernel/env.py` + `lca/infrastructure/env/`

```
lca-kernel/env.py                  # 公共 API:load_layered_env(name, dir)
lca/infrastructure/env/
├── __init__.py                    # 公共面:white_names + load functions
├── bootstrap.py                   # BOOTSTRAP_NAMES + BOOTSTRAP_PREFIXES 常量
└── layered.py                     # 实际 load 逻辑(读 .env,过滤,merge)
```

**分层设计**(避免 kernel 直接管所有 env):
- `lca/infrastructure/env/` 是基础设施层(纯常量 + 纯函数,不依赖 kernel)
- `lca-kernel/env.py` 是 kernel 层的 facade,把基础设施暴露为 `load_layered_env(name, dir)`
- 其他 plugin 需要 env 也走 `ctx.inject('env')`,由 kernel 启动时 provide

### 决定 4:K7 BOOTSTRAP_NAMES 白名单(LCA 版本)

借鉴 deepseek,但适配 Python + LCA 命名:

```python
# lca/infrastructure/env/bootstrap.py

# 这些 key 必须能从 .env 加载(覆盖 ambient env 中已存在的值)
BOOTSTRAP_NAMES: frozenset[str] = frozenset({
    # Python / venv
    "PATH", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
    "PYTHONUSERBASE", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL",
    "UV_PROJECT_ENVIRONMENT", "UV_LINK_MODE",
    # Shell / locale
    "HOME", "USERPROFILE", "SHELL", "LANG", "LC_ALL", "TZ",
    # VCS hooks
    "GIT_SSH", "GIT_SSH_COMMAND", "GIT_EXTERNAL_DIFF",
    "GIT_PAGER", "GIT_EDITOR", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_COUNT",
    "EDITOR", "VISUAL", "PAGER",
    # Network trust
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
    "PYTHONHTTPSVERIFY", "NODE_TLS_REJECT_UNAUTHORIZED",
})

# 这些 prefix 的 key 允许从 .env 加载
BOOTSTRAP_PREFIXES: tuple[str, ...] = (
    "LCA_",            # LCA 自身配置(LCA_PROFILE 走黑名单单独禁)
    "LCA_INTERNAL_",   # LCA 内部 flag(K6/K7/K8 状态)
    "DSH_",            # deepseek 兼容(用户从 DSH 迁移)
    "XDG_",            # freedesktop standard
    "DYLD_",           # macOS dynamic linker
    "LD_",             # Linux dynamic linker
    "BASH_FUNC_",      # bash function exports
    # === LCA 实际部署环境前缀(PR-1 实施前盘点补全,以下为完整候选清单)===
    "LLM_",            # LLM provider config(LLM_API_KEY / LLM_BASE_URL / LLM_MODEL / LLM_API_STYLE)
    "GATEWAY_",        # Gateway transport(GATEWAY_HOST / GATEWAY_PORT / GATEWAY_BIND)
    "LOBE_",           # LobeHub UI(LOBE_HOST / LOBE_DEV_PORT)
    "LOBEHUB_",        # LobeHub release(LOBEHUB_RELEASE)
    "ONLYBOXES_",      # Onlyboxes 沙箱(ONLYBOXES_TERMINAL_IMAGE / ONLYBOXES_WORKER_SERVICE)
    "MARKET_",         # 市场插件(MARKET_CLIENT_ID / MARKET_CLIENT_SECRET)
    "AGENCY_",         # Agent 服务(AGENCY_ROLES_DIR_ENV / AGENCY_TOOL_PERMISSION)
    "WAL_",            # Write-Ahead Log(WAL_PATH / WAL_RETENTION)
    "DB_",             # 数据库(DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD)
    "S3_",             # 对象存储(S3_ENDPOINT / S3_BUCKET / S3_ACCESS_KEY)
    "REDIS_",          # Redis 缓存(REDIS_HOST / REDIS_PORT / REDIS_DB)
    "OTEL_",           # OpenTelemetry(OTEL_EXPORTER_OTLP_ENDPOINT 等标准)
    "VAULT_",          # 密钥管理(VAULT_ADDR / VAULT_TOKEN)
)

# 黑名单(即便在 LCA_ 前缀下也不能从 .env 加载)
BOOTSTRAP_FORBIDDEN: frozenset[str] = frozenset({
    "LCA_PROFILE",                  # 必须由 CLI argv 决定
    "LCA_KERNEL_KEY",",       # 由 profile/secret 体系管
    "LCA_INTERNAL_INJECTION",       # 防止 .env 假装是 kernel 内部 flag
})
```

**核心规则**(抄 deepseek):
1. `.env` 只能覆盖 BOOTSTRAP_NAMES 中**且 ambient env 已存在**的 key(防止新增)
2. `.env` 只能新增 BOOTSTRAP_PREFIXES 中**且 ambient env 不存在**的 key(防止覆盖关键)
3. 任何不匹配白名单的 .env key → 默认 fail-loud(`--allow-unknown-env-keys` 可关闭,但 CI 默认阻断)

### 决定 5:K7 load 函数签名

```python
# lca-kernel/env.py
def load_layered_env(bin_name: str, dir: Path = Path.cwd()) -> EnvSnapshot:
    """Load .env with whitelist enforcement, return immutable snapshot.

    Three layers (deepseek model):
    - Layer 0: ambient os.environ (read-only at this point)
    - Layer 1: <dir>/.env (filtered by BOOTSTRAP_NAMES ∪ BOOTSTRAP_PREFIXES)
    - Layer 2: profile env refs ({from_env: ...} in profile YAML, ADR-0061 §决定 2)

    Returns EnvSnapshot(frozen mapping) — providers see immutable provenance.
    Boot failures: any unknown key in .env → KernelError("unknown env key: %s")
    """
```

`EnvSnapshot` 是 frozen dataclass,挂到 `ctx.inject('env')`,plugin 通过它读 env,**不可写**。

### 决定 6:fail-loud 跟 ShutdownCoordinator 协同

借鉴 deepseek `apps/cli/src/profile-boot.ts:200-230` 的"signal 装在 boot 期也兜底":

```python
# lca-kernel/lifecycle.py
def create_shutdown_coordinator(
    *, kernel: KernelHandle, transports: list[TransportHandle],
) -> ShutdownCoordinator:
    """协调 dispose 顺序:transports 先关 listen,再 kernel dispose,最后 exit。

    transports 关 listen 是为了:
    - 不再接受新请求
    - 让 in-flight 请求自然结束
    - 避免 race:kernel dispose 后 ctx.inject 报错
    """
    coordinator = ShutdownCoordinator()
    signal.signal(signal.SIGTERM, lambda *_: coordinator.interrupt(0))
    signal.signal(signal.SIGINT, lambda *_: coordinator.interrupt(130))
    install_fail_loud(coordinator)
    return coordinator
```

**关键**:`transports` 列表是 transport plugin 在 setup 时 `coordinator.register_transport(self)` 注册的;关闭时 LIFO 反序(最后注册的最先关)。

### 决定 7:`lca/infrastructure/env/` 跟 K7 的关系

**禁止** `lca/infrastructure/env/` 直接读 `os.environ` 或 `Path.cwd()`(违反 ADR-0085 "Plugin 不得自行读取凭证/系统状态"):

```python
# lca/infrastructure/env/bootstrap.py — 纯常量
BOOTSTRAP_NAMES: frozenset[str] = frozenset({...})  # 静态
BOOTSTRAP_PREFIXES: tuple[str, ...] = (...)          # 静态
BOOTSTRAP_FORBIDDEN: frozenset[str] = frozenset({...})  # 静态
# 不 import os, 不读 sys, 不读 dotenv
```

`lca-kernel/env.py` 是**唯一调用 .env 实际加载的位置**;`load_layered_env()` 把 ambient env + .env(白名单过滤)+ profile env refs 三层合并,返回 frozen `EnvSnapshot`。

**plugin 通过 `ctx.inject('env')` 拿 EnvSnapshot**,不直接 import `lca.infrastructure.env.*`。

## 与既有 ADR 的衔接

| 既有 | 衔接 |
|---|---|
| ADR-0062 插件运行时收口 | 本 ADR 是 ADR-0062 §4 "Cordis Fiber Boot + L4 严格闭合" 的 process 侧落地 |
| ADR-0083 W0 / W1 主链收紧 | 本 ADR 是 W1 的 "kernel 必装 fail-loud" 具体落地 |
| ADR-0115 Kernel/Transport 边界 | 本 ADR 是 ADR-0115 决定 1 表中 K6 / K7 的具体实现 |

## CI 门禁

新增 / 复用:

- `tests/lca_kernel/test_lifecycle.py`(新建):
  - SIGTERM → exit 0 + transport 先 dispose + kernel 后 dispose
  - SIGINT → exit 130
  - unhandledRejection → exit 1(但不破坏已 dispose 状态)
  - 双触发(SIGTERM + unhandled)→ 只 dispose 一次
- `tests/lca_kernel/test_env.py`(新建):
  - 白名单 key 从 .env 覆盖 ambient ✓
  - 黑名单 key 从 .env 加载 → KernelError
  - 不匹配任何规则的 key → KernelError(unknown env key)
  - `--allow-unknown-env-keys` 关闭 fail-loud(测试用)
- `tests/lca_kernel/test_shutdown_coordinator.py`(新建):
  - LIFO 反序:transport1 (register 先) → transport2 (register 后),shutdown 后 dispose 顺序是 transport2 → transport1
  - shutdown 期间新的 register_transport 调用被拒绝
- `tests/test_lca_kernel_no_os_kill.py`(新建):`grep -rE 'os.kill|signal.SIGKILL' lca-kernel/` 必须为空(除 `lifecycle.py` 的 signal handler 装卸)
- `tests/test_lca_infrastructure_env_is_pure.py`(新建):`lca/infrastructure/env/bootstrap.py` 不能 import `os` / `sys` / `dotenv`
- `tests/test_no_process_singleton.py`(新建):LCA 全局无 `_shutdown_coordinator = ...` 这类 module-level 单例

## 放弃的方案

- **只在 `gateway/app.py` 装 fail-loud**(在 transport 层,不在 kernel):违反"kernel 零 transport 知识";JSON-RPC / stdio CLI 等其他 transport 各自装一遍,分散。
- **用 `python-dotenv` 默认行为全 open 加载**:深 seek `BOOTSTRAP_NAMES` 模型已被验证,沿用;自创 `python-dotenv` 包装层会引入不必要依赖。
- **K6 / K7 合并到 `_install_observability`**:评审一致反对双源同名不同职;K6 lifecycle 和 K7 env 职责完全不同,合并会让 module 又变成"什么都装" 的反模式。
- **用 `atexit` 注册 shutdown**:Python `atexit` 不支持 async dispose,且不会响应 SIGKILL;沿用 deepseek `install_fail_loud` + signal handler 模式。
- **`lca/infrastructure/env/` 不存在,直接放 `lca-kernel/env.py`**:kernel 模块不该管所有 env;借鉴 deepseek 分层(`app-boot` 内 facade + 静态常量外置),便于 plugin 通过 `ctx.inject('env')` 复用。

## 后果

正面:
- K6 Fail-loud 让生产部署失败可观察、可控;plugin setup 抛异常不再静默
- K7 BOOTSTRAP_NAMES 跟 deepseek 一致;`.env` 行为可审计
- ShutdownCoordinator 单一所有权;transport dispose / kernel dispose / exit code 协调一处管
- env 分层加载 + EnvSnapshot frozen → plugin 拿到的是 immutable provenance

负面:
- K7 BOOTSTRAP_NAMES 白名单需要根据 LCA 实际部署配置收敛(可能漏 `LCA_*` 变量,需要先盘点 LCA 当前所有 .env 变量)
- K6 signal handler 装卸需要在 tests 里小心,否则 tests 收不到 SIGINT
- `lca/infrastructure/env/` 是新目录,需要新增 README + AGENTS.md 仓库地图更新
- env 加载顺序(ambient vs .env vs profile env refs)需要在 CI 测试矩阵覆盖三层组合

## 索引

| 主题 | 文档 |
|---|---|
| deepseek installFailLoud | `~/deepseek-harness/packages/boot/app-boot/src/index.ts` (function installFailLoud) |
| deepseek createProcessShutdown | `~/deepseek-harness/apps/cli/src/profile-boot.ts:204-235` |
| deepseek BOOTSTRAP_NAMES | `~/deepseek-harness/packages/boot/app-boot/src/index.ts:51-99` |
| deepseek loadLayeredEnv | `~/deepseek-harness/packages/boot/app-boot/src/index.ts` (function loadLayeredEnv) |
| LCA kernel 顶层包 | `lca-kernel/` (新建) |
| LCA 现行 dispose 重复实现 | `lca/harness/profile/boot.py:230-240` + `lca/harness/profile/lifespan.py:84-90` + `gateway/app.py` |
| LCA 现行 env 缺失 | `lca/infrastructure/env/` (目录不存在) |
| Kernel/Transport 边界 | [ADR-0115](./0115-kernel-transport-boundary.md) |
| Cordis Patch HMR(后续) | [ADR-0118](./0118-cordis-patch-hmr.md) |